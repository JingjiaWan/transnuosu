import os
from typing import Iterator, List

from openai import OpenAI


class YiToChineseTranslator:
    def __init__(
        self,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        api_key: str | None = "",
        grammar_rules_path: str = "data/yi_grammar_rules.txt",
        chinese_dictionary_path: str = "data/yi_chinese_dictionary.txt",
        english_dictionary_path: str = "data/yi_english_dictionary.txt",
        examples_path: str = "data/yi_chinese_examples.txt"
    ):
        """
        Initialize the Yi to Chinese translator.
        
        Args:
            base_url: The base URL for the API
            model: The model name to use
            api_key: The API key (defaults to DEEPSEEK_API_KEY environment variable)
            dictionary_path: Path to the Yi-Chinese dictionary file
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("DOUBAO_API_KEY")
        self.examples_path = examples_path
        self.grammar_rules_path = grammar_rules_path
        self.english_dictionary_path = english_dictionary_path
        self.chinese_dictionary_path = chinese_dictionary_path
        
        if not self.api_key:
            raise ValueError("API key must be provided or set in DEEPSEEK_API_KEY environment variable")
        
        # Load dictionary
        self.rules = self._load_grammar_rules()
        self.examples = self._load_examples()
        self.english_dictionary = self._load_dictionary(self.english_dictionary_path)
        self.chinese_dictionary = self._load_dictionary(self.chinese_dictionary_path)
    
    def _load_grammar_rules(self) -> List[str]:
        """Load the Yi grammar rules from file."""
        try:
            with open(self.grammar_rules_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Grammar rules file not found at {self.grammar_rules_path}")
            return []
    
    def _load_examples(self) -> List[str]:
        """Load the Yi language examples from file."""
        try:
            with open(self.examples_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Examples file not found at {self.examples_path}")
            return []

    def _load_dictionary(self, dictionary_path)-> List[str]:
        """Load the Yi dictionary from file."""
        try:
            with open(dictionary_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Dictionary file not found at {dictionary_path}")
            return []
    
    def _find_relevant_entries(self, yi_sentence: str, entries: list) -> List[str]:
        """
        Find the most relevant dictionary entries for the given Yi sentence.
        Uses simple word matching - words that appear in the sentence.
        
        Args:
            yi_sentence: The Yi language sentence to translate
            top_k: Number of most relevant entries to return
            
        Returns:
            List of relevant dictionary entries
        """
        if not entries:
            return []
        
        yi_sentence = yi_sentence.replace(" ", "")
        
        # Score each dictionary entry by how many characters match
        relevant_entries: List[str] = []
        for entry in entries :
            # Assume dictionary format is "Yi_word: Chinese_translation" or similar
            yi_part = entry.split('|')[0] if '|' in entry else entry.split()[0] if entry else ""
            yi_part = yi_part.replace(" ", "")

            if yi_part in yi_sentence :  
                relevant_entries.append(entry.strip())
            # # Count matching characters
            # matches = sum(1 for char in yi_part if char in yi_chars)
            # if matches > 0:
            #     scored_entries.append((matches, entry))
        
        return relevant_entries

    def _find_yi_rules(self) -> str:
        """Return Yi degree-intensifying word formation rules for prompt context."""
        return (
            "【彝语程度加强构词法】\n"
            "1. 若词语 A 为形容词或表示性质的词，可通过\"复写 + ꐯ\"构成加强式：\n"
            "   - 模式一：AꐯA\n"
            "   - 模式二：Aꐯ(A 的第二音节)\n"
            "   二者均表示\"非常 A\"。\n\n"
            "2. 示例：\n"
            "   - ꇰ → ꇰꐯꇰ （非常笨）\n"
            "   - ꀑꁮ → ꀑꁮꐯꀑꁮ（非常聪明）\n"
            "   - ꀉꒉ → ꀉꒉꐯꒉ（非常大）\n"
            "   - ꀁꃚ → ꀁꃚꐯꁃꃚ / ꀁꃚꐯꃚ（非常细）\n\n"
            "回答时请：\n"
            "- 自动识别词是否能产生加强式\n"
        )
    
    def translate(self, yi_sentence: str) -> Iterator[str]:
        """
        Translate a Yi language sentence to Chinese in streaming mode.
        
        Args:
            yi_sentence: The Yi language sentence to translate
            
        Yields:
            Chunks of the translated Chinese text
        """
        # Get relevant dictionary entries
        relevant_english_entries = self._find_relevant_entries(yi_sentence, self.english_dictionary)
        relevant_chinese_entries = self._find_relevant_entries(yi_sentence, self.chinese_dictionary)
        relevant_yi_rules = self._find_yi_rules()

        # print("找到相关英文词典条目 :\n", "\n".join(relevant_english_entries))
        print("找到相关中文词典条目 :\n", "\n".join(relevant_chinese_entries))
        
        # Build context from dictionary
        context = ""
        if relevant_english_entries or relevant_chinese_entries:
            context = f"""
参考英文词典条目：
{chr(10).join(relevant_english_entries)}

参考中文词典条目：
{chr(10).join(relevant_chinese_entries)}

参考的彝语规则：
{relevant_yi_rules}
"""
        prompt = f"""{context}请将以下彝语句子先翻译成英文再根据英文翻译中文：

彝语：{yi_sentence}

翻译："""

        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的彝语到中文翻译助手，能准确地将彝语翻译成中文。"
                    },
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )

            content = response.choices[0].message.content if response.choices else ""
            if content:
                yield content
        except Exception as e:
            yield f"翻译错误：{str(e)}"
    
    def translate_complete(self, yi_sentence: str) -> str:
        """
        Translate a Yi language sentence to Chinese and return the complete result.
        
        Args:
            yi_sentence: The Yi language sentence to translate
            
        Returns:
            The complete translated Chinese text
        """
        result = ""
        for chunk in self.translate(yi_sentence):
            result += chunk
        return result


def main():
    """Main function with interactive input."""
    
    print("="*60)
    print("彝语到中文翻译器")
    print("Yi to Chinese Translator")
    print("="*60)
    print()
    
    try:
        # Initialize translator
        translator = YiToChineseTranslator()
        print(f"✓ 翻译器初始化成功")
        print(f"✓ 已加载 {len(translator.english_dictionary)} 条英文词典条目\n")
        print(f"✓ 已加载 {len(translator.chinese_dictionary)} 条中文词典条目\n")
        
    except ValueError as e:
        print(f"✗ 初始化失败: {e}")
        print("请设置 DEEPSEEK_API_KEY 环境变量")
        return
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return
    
    # Interactive loop
    while True:
        print("-"*60)
        yi_sentence = input("请输入彝语句子 (输入 'quit' 或 'exit' 退出):\n> ").strip()
        
        if not yi_sentence:
            print("错误：输入不能为空\n")
            continue
        
        if yi_sentence.lower() in ['quit', 'exit', '退出']:
            print("\n再见！")
            break
        
        print(f"\n正在翻译：{yi_sentence}")
        print("\n翻译结果：")
        print("-"*60)
        
        # Translate in streaming mode
        translation = ""
        for chunk in translator.translate(yi_sentence):
            print(chunk, end='', flush=True)
            translation += chunk
        
        print("\n" + "-"*60)
        print(f"完整翻译：{translation}\n")


if __name__ == "__main__":
    main()
