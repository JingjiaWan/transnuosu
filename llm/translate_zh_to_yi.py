import os
import json
import requests
from typing import Iterator, List, Tuple


class ChineseToYiTranslator:
    def __init__(
        self,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-1-5-pro-32k-250115",
        api_key: str = None,
        grammar_rules_path: str = "data/yi_grammar_rules.txt",
        english_yi_dictionary_path: str = "data/english_yi_dictionary.txt",
        english_yi_examples_path: str = "data/english_yi_examples.txt"
    ):
        """
        Initialize the Chinese to Yi translator.
        
        Args:
            base_url: The base URL for the API
            model: The model name to use
            api_key: The API key (defaults to DOUBAO_API_KEY environment variable)
            grammar_rules_path: Path to the Yi grammar rules file
            chinese_dictionary_path: Path to the Yi-Chinese dictionary file
            english_dictionary_path: Path to the Yi-English dictionary file
            examples_path: Path to the Yi examples file
            english_yi_dictionary_path: Path to the English-Yi dictionary file
            english_yi_examples_path: Path to the English-Yi examples file
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_key = api_key or os.getenv("DOUBAO_API_KEY")
        self.grammar_rules_path = grammar_rules_path
        self.english_yi_dictionary_path = english_yi_dictionary_path
        self.english_yi_examples_path = english_yi_examples_path
        
        if not self.api_key:
            raise ValueError("API key must be provided or set in DOUBAO_API_KEY environment variable")
        
        # API endpoint
        self.api_url = f"{self.base_url}/chat/completions"
        
        # Load dictionary and rules
        self.rules = self._load_grammar_rules()
        self.english_yi_dictionary = self._load_dictionary(self.english_yi_dictionary_path)
        self.english_yi_examples = self._load_examples_from_file(self.english_yi_examples_path)
    
    def _load_grammar_rules(self) -> List[str]:
        """Load the Yi grammar rules from file."""
        try:
            with open(self.grammar_rules_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Grammar rules file not found at {self.grammar_rules_path}")
            return []
    
    def _load_examples_from_file(self, examples_path: str) -> List[str]:
        """Load examples from a specific file path."""
        try:
            with open(examples_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Examples file not found at {examples_path}")
            return []

    def _load_dictionary(self, dictionary_path) -> List[str]:
        """Load the Yi dictionary from file."""
        try:
            with open(dictionary_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Dictionary file not found at {dictionary_path}")
            return []

    def _find_relevant_examples(self, entries: list) -> List[str]:
        """
        Find the most relevant examples for the given dictionary entries.
        Uses simple word matching - words that appear in the entries.
        
        Args:
            entries: The list of dictionary entries to find examples for
        Returns:
            List of relevant examples
        """
        relevant_examples = []
        for example in self.examples:
            for entry in entries:
                # Extract Chinese part from dictionary entry
                chinese_part = entry.split('|')[1] if '|' in entry and len(entry.split('|')) > 1 else ""
                chinese_part = chinese_part.strip()
                
                # Extract Chinese part from example
                example_chinese = example.split('|')[1] if '|' in example and len(example.split('|')) > 1 else ""
                
                # Check if any words from the dictionary entry appear in the example
                if chinese_part and any(word in example_chinese for word in chinese_part.split()):
                    relevant_examples.append(example.strip())
                    break
        return relevant_examples
    
    def _find_relevant_english_examples(self, entries: list) -> List[str]:
        """
        Find the most relevant English-Yi examples for the given dictionary entries.
        Uses simple word matching - words that appear in the entries.
        
        Args:
            entries: The list of dictionary entries to find examples for
        Returns:
            List of relevant examples
        """
        relevant_examples = []
        for example in self.english_yi_examples:
            for entry in entries:
                # Extract English part from dictionary entry
                english_part = entry.split('|')[0] if '|' in entry and len(entry.split('|')) > 1 else ""
                english_part = english_part.strip().lower()
                
                if english_part in example :
                    relevant_examples.append(example.strip())
                    break
        return relevant_examples
    
    def _find_relevant_english_entries(self, english_sentence: str, entries: list) -> List[str]:
        """
        Find the most relevant dictionary entries for the given English sentence.
        Uses simple word matching - words that appear in the sentence.
        
        Args:
            english_sentence: The English sentence to find entries for
            entries: List of dictionary entries
            
        Returns:
            List of relevant dictionary entries
        """
        if not entries:
            return []
        
        relevant_entries = []
        english_sentence_lower = english_sentence.lower()
        english_sentence_words = set([word.strip('.,!?;"\'').lower() for word in english_sentence_lower.split()])

        for entry in entries:
            # Extract English part from dictionary entry (assumes format: Yi|English)
            english_part = entry.split('|')[0] if '|' in entry and len(entry.split('|')) > 1 else ""
            english_part = english_part.strip().lower()
            english_part_words = set([word.strip('.,!?;"\'') for word in english_part.split()])
            
            # Check if any part of the English translation appears in the sentence
            if english_part and any(word in english_sentence_words for word in english_part_words):
                relevant_entries.append(entry.strip())
        
        return relevant_entries

    def translate_chinese_to_english(self, chinese_sentence: str) -> str:
        """
        Translate a Chinese sentence to English using LLM.
        
        Args:
            chinese_sentence: The Chinese sentence to translate
            
        Returns:
            The English translation
        """
        prompt = f"""Please translate the following Chinese sentence to English. Provide only the English translation without any additional explanation.

Chinese: {chinese_sentence}

English:"""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional Chinese to English translator. Provide accurate and natural English translations. Never output anything other than the translation result."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                english_translation = result['choices'][0]['message']['content'].strip()
                return english_translation
            else:
                return f"Translation error: No response from API"
                
        except requests.exceptions.RequestException as e:
            return f"Translation error: {str(e)}"
        except Exception as e:
            return f"Unknown error: {str(e)}"

    def translate_english_to_yi(self, english_sentence: str) -> Iterator[str]:
        """
        Translate an English sentence to Yi language in streaming mode.
        
        Args:
            english_sentence: The English sentence to translate
            
        Yields:
            Chunks of the translated Yi text
        """
        # Get relevant dictionary entries
        relevant_english_yi_entries = self._find_relevant_english_entries(english_sentence, self.english_yi_dictionary)
        relevant_english_yi_examples = self._find_relevant_english_examples(relevant_english_yi_entries)

        print("\n找到相关英文-彝语词典条目:\n", "\n".join(relevant_english_yi_entries))
        print("找到相关英文-彝语例句:\n", "\n".join(relevant_english_yi_examples))
        
        # Build context from dictionary
        context = ""
        if relevant_english_yi_entries or self.rules:
            context = f"""
参考彝语语法规则：
{chr(10).join(self.rules)}

参考英文-彝语词典条目：
{chr(10).join(relevant_english_yi_entries)}

参考的英文-彝语例句：
{chr(10).join(relevant_english_yi_examples)}
"""
        
        # Build the prompt
        prompt = f"""{context}请将以下英文句子翻译成彝语。请严格遵循彝语的语法规则，并参考提供的词典和例句：

英文：{english_sentence}

彝语翻译："""
        
        # Prepare request headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的英文到彝语翻译助手。请根据提供的彝语语法规则、词典参考和例句，准确地将英文翻译成彝语。请确保翻译符合彝语的语法和表达习惯。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": True
        }
        
        try:
            # Make streaming request
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            # Process streaming response
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    
                    # Skip empty lines and comments
                    if not line.strip() or line.strip().startswith(':'):
                        continue
                    
                    # Remove "data: " prefix
                    if line.startswith('data: '):
                        line = line[6:]
                    
                    # Check for end of stream
                    if line.strip() == '[DONE]':
                        break
                    
                    try:
                        # Parse JSON chunk
                        chunk_data = json.loads(line)
                        
                        # Extract content from chunk
                        if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                            delta = chunk_data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            
                            if content:
                                yield content
                    
                    except json.JSONDecodeError:
                        # Skip malformed JSON
                        continue
                        
        except requests.exceptions.RequestException as e:
            yield f"翻译错误：{str(e)}"
        except Exception as e:
            yield f"未知错误：{str(e)}"
    
    def translate(self, chinese_sentence: str) -> Iterator[str]:
        """
        Translate a Chinese sentence to Yi language in streaming mode.
        Uses two-step translation: Chinese → English → Yi
        
        Args:
            chinese_sentence: The Chinese sentence to translate
            
        Yields:
            Chunks of the translated Yi text
        """
        # Step 1: Translate Chinese to English
        print("\n步骤 1: 翻译中文到英文...")
        english_translation = self.translate_chinese_to_english(chinese_sentence)
        print(f"英文翻译: {english_translation}\n")
        
        if english_translation.startswith("Translation error:") or english_translation.startswith("Unknown error:"):
            yield english_translation
            return
        
        # Step 2: Translate English to Yi
        print("步骤 2: 翻译英文到彝语...")
        for chunk in self.translate_english_to_yi(english_translation):
            yield chunk
    
    def translate_complete(self, chinese_sentence: str) -> str:
        """
        Translate a Chinese sentence to Yi language and return the complete result.
        
        Args:
            chinese_sentence: The Chinese sentence to translate
            
        Returns:
            The complete translated Yi text
        """
        result = ""
        for chunk in self.translate(chinese_sentence):
            result += chunk
        return result


def main():
    """Main function with interactive input."""
    
    print("="*60)
    print("中文到彝语翻译器")
    print("Chinese to Yi Translator")
    print("="*60)
    print()
    
    try:
        # Initialize translator
        translator = ChineseToYiTranslator(
            model="deepseek-v3-1-terminus", 
        )
        print(f"✓ 翻译器初始化成功")
        print(f"✓ 已加载 {len(translator.english_yi_dictionary)} 条英文-彝语词典条目")
        print(f"✓ 已加载 {len(translator.rules)} 条语法规则")
        print(f"✓ 已加载 {len(translator.english_yi_examples)} 条英文例句\n")
        
    except ValueError as e:
        print(f"✗ 初始化失败: {e}")
        print("请设置 DOUBAO_API_KEY 环境变量")
        return
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return
    
    # Interactive loop
    while True:
        print("-"*60)
        chinese_sentence = input("请输入中文句子 (输入 'quit' 或 'exit' 退出):\n> ").strip()
        
        if not chinese_sentence:
            print("错误：输入不能为空\n")
            continue
        
        if chinese_sentence.lower() in ['quit', 'exit', '退出']:
            print("\n再见！")
            break
        
        print(f"\n正在翻译：{chinese_sentence}")
        print("\n翻译结果：")
        print("-"*60)
        
        # Translate in streaming mode
        translation = ""
        for chunk in translator.translate(chinese_sentence):
            print(chunk, end='', flush=True)
            translation += chunk
        
        print("\n" + "-"*60)
        print(f"完整翻译：{translation}\n")


if __name__ == "__main__":
    main()