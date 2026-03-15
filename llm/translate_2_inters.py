import os
import json
import requests
from typing import Iterator, List


class YiToChineseTranslator:
    def __init__(
        self,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        model: str = "doubao-1-5-pro-32k-250115",
        dictionary_model: str = "doubao-1-5-pro-256k-250115",
        api_key: str = None,
        dictionary_path: str = "data/yi_chinese_dictionary.txt"
    ):
        """
        Initialize the Yi to Chinese translator.
        
        Args:
            base_url: The base URL for the API
            model: The model name to use for translation
            dictionary_model: The model name to use for dictionary extraction
            api_key: The API key (defaults to DOUBAO_API_KEY environment variable)
            dictionary_path: Path to the Yi-Chinese dictionary file
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.dictionary_model = dictionary_model
        self.api_key = api_key or os.getenv("DOUBAO_API_KEY")
        self.dictionary_path = dictionary_path
        
        if not self.api_key:
            raise ValueError("API key must be provided or set in DOUBAO_API_KEY environment variable")
        
        # API endpoint
        self.api_url = f"{self.base_url}/chat/completions"
        
        # Load dictionary
        self.dictionary = self._load_dictionary()
    
    def _load_dictionary(self) -> List[str]:
        """Load the Yi-Chinese dictionary from file."""
        try:
            with open(self.dictionary_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"Warning: Dictionary file not found at {self.dictionary_path}")
            return []
    
    def _call_api_non_streaming(self, messages: List[dict], model: str = None) -> str:
        """
        Call the API in non-streaming mode and return the complete response.
        
        Args:
            messages: List of message dictionaries
            model: Model to use (defaults to self.model)
            
        Returns:
            Complete response text
        """
        if model is None:
            model = self.model
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": model,
            "messages": messages,
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
                return result['choices'][0]['message']['content']
            else:
                return ""
                
        except Exception as e:
            print(f"API调用错误: {e}")
            return ""
    
    def _extract_relevant_entries_with_llm(self, yi_sentence: str, top_k: int = 10) -> List[str]:
        """
        Use LLM to extract the most relevant dictionary entries for the given Yi sentence.
        
        Args:
            yi_sentence: The Yi language sentence to translate
            top_k: Number of most relevant entries to return
            
        Returns:
            List of relevant dictionary entries
        """
        if not self.dictionary:
            return []
        
        # Prepare the dictionary content
        dictionary_content = "\n".join([f"{i+1}. {entry}" for i, entry in enumerate(self.dictionary)])
        
        # Build the prompt for dictionary extraction
        prompt = f"""你是一个彝语专家。我有一个彝语到中文的词典，包含 {len(self.dictionary)} 条记录。

现在我需要翻译以下彝语句子：
"{yi_sentence}"

词典内容：
{dictionary_content}

请从上述词典中选择最相关的 {top_k} 条记录，这些记录对翻译这个彝语句子最有帮助。
只需要输出选中的词典条目的完整内容，每行一条，不要添加序号或其他说明。
如果词典中没有相关的条目，请输出"无相关条目"。"""

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的彝语词典专家，能够准确识别哪些词典条目对翻译特定句子最有帮助。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        print(f"正在使用 {self.dictionary_model} 提取相关词典条目...")
        
        # Call API to get relevant entries
        response = self._call_api_non_streaming(messages, model=self.dictionary_model)
        
        if not response or response.strip() == "无相关条目":
            return []
        
        # Parse the response to get individual entries
        relevant_entries = []
        for line in response.strip().split('\n'):
            line = line.strip()
            # Remove leading numbers and dots if present (e.g., "1. entry" -> "entry")
            if line and not line.startswith('无'):
                # Remove potential numbering
                parts = line.split('. ', 1)
                if len(parts) == 2 and parts[0].isdigit():
                    line = parts[1]
                relevant_entries.append(line)
        
        print(f"✓ 已提取 {len(relevant_entries)} 条相关词典条目\n")
        
        return relevant_entries[:top_k]
    
    def translate(self, yi_sentence: str) -> Iterator[str]:
        """
        Translate a Yi language sentence to Chinese in streaming mode.
        
        Args:
            yi_sentence: The Yi language sentence to translate
            
        Yields:
            Chunks of the translated Chinese text
        """
        # Get relevant dictionary entries using LLM
        relevant_entries = self._extract_relevant_entries_with_llm(yi_sentence)
        
        # Build context from dictionary
        context = ""
        if relevant_entries:
            context = "参考词典条目：\n" + "\n".join(relevant_entries) + "\n\n"
            print("使用的词典条目：")
            for entry in relevant_entries:
                print(f"  - {entry}")
            print()
        
        # Build the prompt
        prompt = f"""{context}请将以下彝语句子翻译成中文：

彝语：{yi_sentence}

中文："""
        
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
                    "content": "你是一个专业的彝语到中文翻译助手。请根据提供的词典参考，准确地将彝语翻译成中文。"
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
    print("彝语到中文翻译器 (智能词典提取)")
    print("Yi to Chinese Translator (Intelligent Dictionary Extraction)")
    print("="*60)
    print()
    
    try:
        # Initialize translator
        translator = YiToChineseTranslator()
        print(f"✓ 翻译器初始化成功")
        print(f"✓ 已加载 {len(translator.dictionary)} 条词典条目")
        print(f"✓ 词典提取模型: {translator.dictionary_model}")
        print(f"✓ 翻译模型: {translator.model}\n")
        
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
        yi_sentence = input("请输入彝语句子 (输入 'quit' 或 'exit' 退出):\n> ").strip()
        
        if not yi_sentence:
            print("错误：输入不能为空\n")
            continue
        
        if yi_sentence.lower() in ['quit', 'exit', '退出']:
            print("\n再见！")
            break
        
        print(f"\n正在翻译：{yi_sentence}\n")
        
        # Translate in streaming mode
        print("翻译结果：")
        print("-"*60)
        translation = ""
        for chunk in translator.translate(yi_sentence):
            print(chunk, end='', flush=True)
            translation += chunk
        
        print("\n" + "-"*60)
        print(f"完整翻译：{translation}\n")


if __name__ == "__main__":
    main()