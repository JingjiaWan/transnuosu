import logging
import os
import re
import secrets
import sqlite3
import sys
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

# Ensure the local llm module is importable when running from the web/ directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LLM_DIR = os.path.join(BASE_DIR, "llm")
if LLM_DIR not in sys.path:
    sys.path.insert(0, LLM_DIR)

# TODO: 如果 translate_yi_to_zh.py 中已有 translate_yi_to_zh 函数且返回结构不同，请在此处适配
try:
    from translate_yi_to_zh import translate_yi_to_zh  # type: ignore
except Exception as exc:  # capture import errors (e.g., missing openai)
    logger = logging.getLogger(__name__)
    logger.warning("translate_yi_to_zh import failed: %s", exc)
    translate_yi_to_zh = None  # type: ignore

try:
    from translate_yi_to_zh import YiToChineseTranslator  # type: ignore
except Exception as exc:
    logger = logging.getLogger(__name__)
    logger.warning("YiToChineseTranslator import failed: %s", exc)
    YiToChineseTranslator = None  # type: ignore

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_translator_instance: Optional[Any] = None
MAX_TEXT_LENGTH = 2000
DB_PATH = os.path.join(BASE_DIR, "feedback.db")


def _get_translator() -> Any:
    """Lazily initialize the translator class defined in llm/translate_yi_to_zh.py."""
    global _translator_instance
    if _translator_instance is None and YiToChineseTranslator is not None:
        data_dir = os.path.join(LLM_DIR, "data")
        base_url = os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com"
        # Default to translate_yi_to_zh.py constructor
        model_name = os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
        _translator_instance = YiToChineseTranslator(
            base_url=base_url,
            model=model_name,
            grammar_rules_path=os.path.join(data_dir, "yi_grammar_rules.txt"),
            chinese_dictionary_path=os.path.join(data_dir, "yi_chinese_dictionary.txt"),
            english_dictionary_path=os.path.join(data_dir, "yi_english_dictionary.txt"),
            examples_path=os.path.join(data_dir, "yi_chinese_examples.txt"),
        )
        logger.info("Translator initialized with base_url=%s, model=%s", base_url, model_name)
    return _translator_instance


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS accepted_translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                yi_text TEXT NOT NULL,
                model_zh_translation TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS corrected_translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                yi_text TEXT NOT NULL,
                model_zh_translation TEXT,
                corrected_zh_translation TEXT NOT NULL,
                user_name TEXT,
                user_email TEXT
            );
            """
        )
        _migrate_feedback_tables(conn)
        conn.commit()
    finally:
        conn.close()


def _get_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _rebuild_table(conn: sqlite3.Connection, table: str, create_sql: str, copy_sql: str) -> None:
    temp_table = f"{table}_old"
    conn.execute(f"ALTER TABLE {table} RENAME TO {temp_table}")
    conn.execute(create_sql)
    conn.execute(copy_sql)
    conn.execute(f"DROP TABLE {temp_table}")


def _migrate_feedback_tables(conn: sqlite3.Connection) -> None:
    accepted_columns = _get_table_columns(conn, "accepted_translations")
    desired_accepted_columns = ["id", "created_at", "yi_text", "model_zh_translation"]
    if accepted_columns != desired_accepted_columns:
        _rebuild_table(
            conn,
            "accepted_translations",
            """
            CREATE TABLE accepted_translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                yi_text TEXT NOT NULL,
                model_zh_translation TEXT NOT NULL
            )
            """,
            """
            INSERT INTO accepted_translations (id, created_at, yi_text, model_zh_translation)
            SELECT
                id,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                yi_text,
                COALESCE(model_zh_translation, zh_translation)
            FROM accepted_translations_old
            """,
        )

    corrected_columns = _get_table_columns(conn, "corrected_translations")
    desired_corrected_columns = [
        "id",
        "created_at",
        "yi_text",
        "model_zh_translation",
        "corrected_zh_translation",
        "user_name",
        "user_email",
    ]
    if corrected_columns != desired_corrected_columns:
        _rebuild_table(
            conn,
            "corrected_translations",
            """
            CREATE TABLE corrected_translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                yi_text TEXT NOT NULL,
                model_zh_translation TEXT,
                corrected_zh_translation TEXT NOT NULL,
                user_name TEXT,
                user_email TEXT
            )
            """,
            """
            INSERT INTO corrected_translations (
                id,
                created_at,
                yi_text,
                model_zh_translation,
                corrected_zh_translation,
                user_name,
                user_email
            )
            SELECT
                id,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                yi_text,
                model_zh_translation,
                corrected_zh_translation,
                user_name,
                user_email
            FROM corrected_translations_old
            """,
        )


init_db()


def _normalize_tokens(tokens: Any) -> List[Dict[str, Any]]:
    """Normalize token/dictionary entries into a frontend-friendly structure."""
    normalized: List[Dict[str, Any]] = []
    if not tokens:
        return normalized

    for token in tokens:
        if not isinstance(token, dict):
            continue
        normalized.append(
            {
                "yi": token.get("yi") or token.get("word") or "",
                "latin": token.get("pinyin") or token.get("latin") or token.get("romanization") or "",
                "pos": token.get("pos") or "",
                "zh": token.get("zh") or token.get("definition") or "",
                "example": token.get("example") or token.get("extra") or "",
            }
        )
    return normalized


def _parse_dict_entry(raw_entry: str) -> Dict[str, str]:
    """
    Parse a raw dictionary line like 'ꀀ | Chinese: ...' into structured fields.
    This is best-effort and keeps unknown parts in the zh field.
    """
    if not raw_entry:
        return {"yi": "", "latin": "", "pos": "", "zh": raw_entry, "example": ""}
    parts = [p.strip() for p in raw_entry.split("|") if p.strip()]
    yi = parts[0] if parts else raw_entry
    zh = ""
    if len(parts) > 1:
        # Join remaining parts as definition.
        zh = " | ".join(parts[1:])
    else:
        zh = raw_entry
    return {"yi": yi, "latin": "", "pos": "", "zh": zh, "example": ""}


def _build_entries_from_translator(translator: Any, text: str) -> List[Dict[str, Any]]:
    """Use the translator's dictionaries to build best-effort entries."""
    if translator is None or not hasattr(translator, "_find_relevant_entries"):
        return []
    try:
        en_entries = translator._find_relevant_entries(text, getattr(translator, "english_dictionary", []))
        zh_entries = translator._find_relevant_entries(text, getattr(translator, "chinese_dictionary", []))
        combined = []
        seen = set()
        for item in en_entries + zh_entries:
            parsed = _parse_dict_entry(item)
            key = (parsed["yi"], parsed["zh"])
            if key in seen:
                continue
            seen.add(key)
            combined.append(parsed)
        return combined
    except Exception as exc:
        logger.warning("Failed to build dictionary entries: %s", exc)
        return []


def run_translation(text: str) -> Dict[str, Any]:
    """
    Perform Yi -> Chinese translation using the existing llm module.
    Returns a unified dict for frontend consumption.
    """
    if translate_yi_to_zh:
        # Prefer a direct helper if it exists.
        result = translate_yi_to_zh(text)  # type: ignore
        translation = ""
        tokens: List[Dict[str, Any]] = []

        if isinstance(result, dict):
            translation = result.get("translation") or result.get("result") or ""
            tokens = _normalize_tokens(result.get("tokens") or result.get("dictionary_entries"))
        elif isinstance(result, str):
            translation = result

        if translation.strip().startswith(("翻译错误", "未知错误")) or translation.strip().lower().startswith("error"):
            raise RuntimeError(translation)

        if not tokens:
            tokens = _build_entries_from_translator(_get_translator(), text)

        return {"translation": translation, "dictionary_entries": tokens}

    translator = _get_translator()
    if translator is None:
        raise RuntimeError("Translator backend not available. 请检查 llm/translate_yi_to_zh.py")

    translation = translator.translate_complete(text)
    if translation.strip().startswith(("翻译错误", "未知错误")) or translation.strip().lower().startswith("error"):
        raise RuntimeError(translation)
    entries = _build_entries_from_translator(translator, text)
    return {"translation": translation, "dictionary_entries": entries}


def _validate_feedback_text(text: str, field_name: str) -> Optional[str]:
    value = (text or "").strip()
    if not value:
        return f"{field_name}不能为空"
    if len(value) > MAX_TEXT_LENGTH:
        return f"{field_name}过长，请控制在 {MAX_TEXT_LENGTH} 字以内"
    return None


def _strip_markdown(text: str) -> str:
    value = (text or "").replace("\r\n", "\n").strip()
    if not value:
        return ""

    value = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip("`"), value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[-*+]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\d+\.\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"\*([^*]+)\*", r"\1", value)
    value = re.sub(r"_([^_]+)_", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _validate_email(email: str) -> Optional[str]:
    value = (email or "").strip()
    if not value:
        return "邮箱不能为空"
    if len(value) > 255:
        return "邮箱过长"
    if "@" not in value or "." not in value.split("@")[-1]:
        return "请输入有效的邮箱地址"
    return None


def _validate_username(username: str) -> Optional[str]:
    value = (username or "").strip()
    if len(value) > 100:
        return "用户名过长"
    return None


def _get_current_user() -> Optional[Dict[str, Any]]:
    user = session.get("user")
    if not isinstance(user, dict):
        return None
    return {
        "id": user.get("id"),
        "username": user.get("username") or "",
        "email": user.get("email") or "",
        "display_name": user.get("username") or user.get("email") or "",
    }


def _upsert_user(username: str, email: str) -> Dict[str, Any]:
    normalized_username = (username or "").strip()
    normalized_email = (email or "").strip().lower()

    conn = get_db_connection()
    try:
        row = conn.execute("SELECT id, username, email FROM users WHERE email = ?", (normalized_email,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (normalized_username or row["username"], row["id"]),
            )
            user_id = row["id"]
            final_username = normalized_username or row["username"] or ""
        else:
            cursor = conn.execute(
                "INSERT INTO users (username, email) VALUES (?, ?)",
                (normalized_username, normalized_email),
            )
            user_id = cursor.lastrowid
            final_username = normalized_username
        conn.commit()
        return {
            "id": user_id,
            "username": final_username,
            "email": normalized_email,
            "display_name": final_username or normalized_email,
        }
    finally:
        conn.close()


@app.route("/api/chatbot", methods=["POST"])
def chatbot_api():
    """
    接收中文输入，返回占位聊天回复。
    如需对接真实大模型，请在此处调用并返回回复文本。
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return jsonify({"success": False, "reply": "", "error": "请输入中文文本"}), 400

        # TODO: Replace with real LLM call.
        reply = f"🤖 回复：{text}"
        return jsonify({"success": True, "reply": reply, "error": None}), 200
    except Exception as exc:
        logger.exception("Chatbot failed: %s", exc)
        return jsonify({"success": False, "reply": "", "error": str(exc)}), 500


@app.route("/", methods=["GET"])
def index():
    """Render the main page."""
    return render_template("index.html", current_user=_get_current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", current_user=_get_current_user(), error=None, form_data={})

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()

    username_error = _validate_username(username)
    if username_error:
        return render_template(
            "login.html",
            current_user=_get_current_user(),
            error=username_error,
            form_data={"username": username, "email": email},
        ), 400

    email_error = _validate_email(email)
    if email_error:
        return render_template(
            "login.html",
            current_user=_get_current_user(),
            error=email_error,
            form_data={"username": username, "email": email},
        ), 400

    user = _upsert_user(username, email)
    session["user"] = {"id": user["id"], "username": user["username"], "email": user["email"]}
    return redirect(url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))


@app.route("/api/me", methods=["GET"])
def api_me():
    return jsonify({"success": True, "data": {"user": _get_current_user()}, "error": None}), 200


@app.route("/api/translate", methods=["POST"])
def api_translate():
    """Handle translation requests."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        text = (payload.get("text") or "").strip()

        if not text:
            return (
                jsonify({"success": False, "data": None, "error": "请输入彝语文本"}),
                400,
            )

        if len(text) > MAX_TEXT_LENGTH:
            return (
                jsonify({"success": False, "data": None, "error": "输入过长，请控制在 2000 字以内"}),
                400,
            )

        translation_result = run_translation(text)
        response = {
            "success": True,
            "data": {
                "original": text,
                "translation": translation_result.get("translation", ""),
                "dictionary_entries": translation_result.get("dictionary_entries", []),
            },
            "error": None,
        }
        return jsonify(response), 200

    except Exception as exc:  # Catch and log any unexpected error.
        logger.exception("Translation failed: %s", exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500


@app.route("/api/feedback/accept", methods=["POST"])
def api_feedback_accept():
    """Store accepted Yi -> Chinese translations."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        yi_text = (payload.get("yi_text") or "").strip()
        model_zh_translation = _strip_markdown(
            payload.get("model_zh_translation")
            or payload.get("zh_translation")
            or ""
        )

        for value, field_name in (
            (yi_text, "彝语原文"),
            (model_zh_translation, "中文翻译"),
        ):
            error = _validate_feedback_text(value, field_name)
            if error:
                return jsonify({"success": False, "error": error}), 400

        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO accepted_translations (yi_text, model_zh_translation)
                VALUES (?, ?)
                """,
                (yi_text, model_zh_translation),
            )
            conn.commit()
            feedback_id = cursor.lastrowid
        finally:
            conn.close()

        return jsonify({"success": True, "data": {"feedback_id": feedback_id}, "error": None}), 200
    except Exception as exc:
        logger.exception("Accept feedback failed: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/feedback/correct", methods=["POST"])
def api_feedback_correct():
    """Store user-corrected Yi -> Chinese translations."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        yi_text = (payload.get("yi_text") or "").strip()
        model_zh_translation = _strip_markdown(payload.get("model_zh_translation") or "")
        corrected_zh_translation = _strip_markdown(payload.get("corrected_zh_translation") or "")
        current_user = _get_current_user()

        for value, field_name in (
            (yi_text, "彝语原文"),
            (model_zh_translation, "模型中文翻译"),
            (corrected_zh_translation, "修正后的中文翻译"),
        ):
            error = _validate_feedback_text(value, field_name)
            if error:
                return jsonify({"success": False, "error": error}), 400

        if not current_user:
            return jsonify({"success": False, "error": "请先登录后再提交修正翻译"}), 401

        conn = get_db_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO corrected_translations (
                    yi_text,
                    model_zh_translation,
                    corrected_zh_translation,
                    user_name,
                    user_email
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    yi_text,
                    model_zh_translation,
                    corrected_zh_translation,
                    current_user["username"] or None,
                    current_user["email"],
                ),
            )
            conn.commit()
            feedback_id = cursor.lastrowid
        finally:
            conn.close()

        return jsonify(
            {
                "success": True,
                "data": {
                    "feedback_id": feedback_id,
                    "user_name": current_user["username"],
                    "user_email": current_user["email"],
                },
                "error": None,
            }
        ), 200
    except Exception as exc:
        logger.exception("Correction feedback failed: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
