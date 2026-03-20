import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="检查本地 Chroma 数据库是否有入库数据")
    parser.add_argument(
        "--path",
        default="chroma",
        help="Chroma 持久化目录路径（默认: chroma）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="每个 collection 展示前 N 条内容（默认: 5）",
    )
    args = parser.parse_args()

    db_path = Path(args.path).resolve()

    if not db_path.exists():
        print(f"[ERROR] 路径不存在: {db_path}")
        print("[TIP] 请确认 --path 是否正确，例如: --path ./chroma")
        return 1

    try:
        import chromadb
    except Exception as e:
        print("[ERROR] 未安装 chromadb，请先安装: pip install chromadb")
        print(f"[DETAIL] {type(e).__name__}: {e}")
        return 2

    try:
        client = chromadb.PersistentClient(path=str(db_path))
        collections = client.list_collections()

        if not collections:
            print(f"[INFO] Chroma目录存在，但没有任何 collection: {db_path}")
            return 0

        print(f"[INFO] Chroma 路径: {db_path}")
        print(f"[INFO] 发现 collection 数量: {len(collections)}")
        print("-" * 80)

        total_count = 0

        for c in collections:
            col = client.get_collection(name=c.name)
            count = col.count()
            total_count += count

            print(f"collection: {c.name}")
            print(f"  count: {count}")

            if count > 0:
                limit = min(args.limit, count)
                sample = col.get(limit=limit, include=["documents", "metadatas"])
                ids = sample.get("ids", [])
                docs = sample.get("documents", [])
                metas = sample.get("metadatas", [])

                print(f"  top {limit} records:")
                for i in range(limit):
                    sample_id = ids[i] if i < len(ids) else None
                    sample_doc = docs[i] if i < len(docs) else None
                    sample_meta = metas[i] if i < len(metas) else None

                    print(f"    [{i+1}] id: {sample_id}")
                    print(f"        doc: {repr(sample_doc)[:200]}")
                    print(f"        meta: {sample_meta}")

            print("-" * 80)

        if total_count > 0:
            print(f"[SUCCESS] 已检测到入库数据，总记录数: {total_count}")
        else:
            print("[INFO] 存在 collection，但记录数为 0")

        return 0

    except Exception as e:
        print("[ERROR] 读取 Chroma 数据库失败")
        print(f"[DETAIL] {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
