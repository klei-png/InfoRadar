import logging
from datetime import datetime, timezone

from src.db.connection import get_conn, init_db
from src.db.repository import insert_items, fetch_candidates_for_agent
from src.models.schema import Item

# 配置日志，方便看报错
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
    print("1. 正在初始化数据库表...")
    init_db()
    print("✅ 数据库表创建成功（或已存在）\n")

    print("2. 正在连接数据库...")
    conn = get_conn()
    print("✅ 连接成功\n")

    # 构造两条测试数据
    now = datetime.now(timezone.utc)
    test_items = [
        Item(
            source_id="test_source_1",
            external_id="test_ext_001",
            url="https://example.com/article/123?utm_source=twitter",
            title="OpenAI 发布 GPT-5 模型",
            snippet="这是一个关于 GPT-5 发布的测试摘要。",
            fetched_at=now,
            category="ai"
        ),
        Item(
            source_id="test_source_2",
            external_id="test_ext_002",
            url="https://finance.example.com/news/456",
            title="美联储宣布降息 25 个基点",
            snippet="这是一个关于美联储降息的测试摘要。",
            fetched_at=now,
            category="finance"
        )
    ]

    print("3. 第一次插入数据（预期成功 2 条）...")
    inserted = insert_items(conn, test_items)
    print(f"✅ 实际插入: {inserted} 条\n")

    print("4. 第二次插入相同数据（预期成功 0 条，触发唯一约束去重）...")
    inserted_again = insert_items(conn, test_items)
    print(f"✅ 实际插入: {inserted_again} 条\n")

    print("5. 测试拉取给 Agent 的候选池...")
    # 这里稍微修改一下 SQL 条件，确保能查出刚刚插入的数据
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, category, title, url FROM items 
            WHERE source_id LIKE 'test_source_%' 
            ORDER BY id DESC LIMIT 5
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"   - [{row[1]}] {row[2]} | URL: {row[3]}")
    print("✅ 候选池拉取成功\n")

    # 清理测试数据（可选，避免污染真实数据库）
    print("6. 清理测试数据...")
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM items WHERE source_id LIKE 'test_source_%'")
    conn.commit()
    print("✅ 清理完成")

    conn.close()

if __name__ == "__main__":
    main()