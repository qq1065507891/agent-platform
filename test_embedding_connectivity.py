import os
import sys
from openai import OpenAI


def main() -> int:
    """测试 ModelScope Embedding 接口联通性。"""
    base_url = os.getenv(
        "MODELSCOPE_BASE_URL",
        "https://ms-ens-59cfd1a0-e1fd.api-inference.modelscope.cn/v1",
    )
    api_key = os.getenv("MODELSCOPE_API_KEY", "ms-7b8a5fb0-25a1-4112-87f6-a5c83a84679d")
    model = os.getenv("MODELSCOPE_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    text = os.getenv("EMBEDDING_TEST_TEXT", "你好")

    if not api_key:
        print("[ERROR] 请先设置环境变量 MODELSCOPE_API_KEY")
        return 1

    print("[INFO] 开始测试 Embedding 接口联通性...")
    print(f"[INFO] base_url={base_url}")
    print(f"[INFO] model={model}")

    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.embeddings.create(
            model=model,
            input=text,
            encoding_format="float",
        )

        embedding = response.data[0].embedding if response.data else []
        print("[SUCCESS] 接口可用")
        print(f"[INFO] 向量维度: {len(embedding)}")
        print(f"[INFO] 前5个值: {embedding[:5]}")
        print(f"[INFO] 完整响应对象: {response}")
        return 0

    except Exception as exc:
        print("[ERROR] 接口调用失败")
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
