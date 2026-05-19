"""
Golden Test 验收脚本
用法：python tests/validate.py
"""

import sys
import requests

BASE_URL = "http://localhost:8000"

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        print(f"{GREEN}✅ PASS{RESET} {name}")
        passed += 1
    else:
        print(f"{RED}❌ FAIL{RESET} {name}" + (f"  ← {detail}" if detail else ""))
        failed += 1


# ════════════════════════════════════════════
# Phase 0：服务启动
# ════════════════════════════════════════════
def test_phase0():
    print(f"\n{YELLOW}=== Phase 0 验收：服务启动 + 文档加载 ==={RESET}")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        check("服务可达（GET /）", r.status_code == 200)
    except Exception as e:
        check("服务可达（GET /）", False, str(e))
        return

    r = requests.get(f"{BASE_URL}/v1/", timeout=5)
    check("v1 页面可访问", r.status_code == 200)


# ════════════════════════════════════════════
# Phase 1：关键词搜索
# ════════════════════════════════════════════
def test_phase1():
    print(f"\n{YELLOW}=== Phase 1 验收：关键词搜索 ==={RESET}")

    # q=OOM → sop-001
    r = requests.get(f"{BASE_URL}/v1/search?q=OOM", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=OOM 返回 sop-001", "sop-001" in ids, f"实际: {ids}")

    # q=故障 → 多个文档
    r = requests.get(f"{BASE_URL}/v1/search?q=%E6%95%85%E9%9A%9C", timeout=5)
    data = r.json()
    check("q=故障 返回多个文档(>=3)", len(data["results"]) >= 3,
          f"实际返回 {len(data['results'])} 个")

    # q=replication → 空（仅在 script 标签内）
    r = requests.get(f"{BASE_URL}/v1/search?q=replication", timeout=5)
    data = r.json()
    check("q=replication 返回空", len(data["results"]) == 0,
          f"实际: {[res['id'] for res in data['results']]}")

    # q=CDN → sop-003 和 sop-010
    r = requests.get(f"{BASE_URL}/v1/search?q=CDN", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=CDN 包含 sop-003", "sop-003" in ids, f"实际: {ids}")
    check("q=CDN 包含 sop-010", "sop-010" in ids, f"实际: {ids}")

    # q=& → 解析正确 + 返回含 & 文档
    r = requests.get(f"{BASE_URL}/v1/search?q=%26", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=& 查询词正确解析", data["query"] == "&",
          f"实际解析: '{data['query']}'")
    check("q=& 返回 sop-003 或 sop-010",
          "sop-003" in ids or "sop-010" in ids, f"实际: {ids}")


# ════════════════════════════════════════════
# Phase 2：语义搜索
# ════════════════════════════════════════════
def test_phase2():
    print(f"\n{YELLOW}=== Phase 2 验收：语义搜索 ==={RESET}")

    # 先确认 v2 服务可用
    try:
        r = requests.get(f"{BASE_URL}/v2/", timeout=5)
        check("v2 页面可访问", r.status_code == 200)
    except Exception as e:
        check("v2 页面可访问", False, str(e))
        return

    def semantic_search(query: str) -> list[dict]:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        r = requests.get(f"{BASE_URL}/v2/search?q={encoded}", timeout=30)
        return r.json().get("results", [])

    def top3_ids(results: list[dict]) -> list[str]:
        return [r["id"] for r in results[:3]]

    def top5_ids(results: list[dict]) -> list[str]:
        return [r["id"] for r in results[:5]]

    # Case 1: "服务器挂了" → sop-001 或 sop-004 在前 3
    results = semantic_search("服务器挂了")
    ids_top3 = top3_ids(results)
    check(
        "q=服务器挂了：sop-001 或 sop-004 在前 3",
        "sop-001" in ids_top3 or "sop-004" in ids_top3,
        f"前3: {ids_top3}，全部: {top5_ids(results)}"
    )

    # Case 2: "黑客攻击" → sop-005 在前 3
    results = semantic_search("黑客攻击")
    ids_top3 = top3_ids(results)
    check(
        "q=黑客攻击：sop-005 在前 3",
        "sop-005" in ids_top3,
        f"前3: {ids_top3}，全部: {top5_ids(results)}"
    )

    # Case 3: "机器学习模型出问题" → sop-008 在前 3
    results = semantic_search("机器学习模型出问题")
    ids_top3 = top3_ids(results)
    check(
        "q=机器学习模型出问题：sop-008 在前 3",
        "sop-008" in ids_top3,
        f"前3: {ids_top3}，全部: {top5_ids(results)}"
    )

    # Case 4: 返回结果有 score 字段且有序
    results = semantic_search("数据库故障")
    if results:
        scores = [r["score"] for r in results]
        check(
            "语义搜索结果按 score 降序排列",
            scores == sorted(scores, reverse=True),
            f"scores: {scores[:5]}"
        )
        check(
            "语义搜索结果包含 score 字段(0~1之间)",
            all(0 <= s <= 1 for s in scores),
            f"scores: {scores[:5]}"
        )

# ════════════════════════════════════════════
# Phase 3：Agent 对话
# ════════════════════════════════════════════
def test_phase3():
    print(f"\n{YELLOW}=== Phase 3 验收：Agent 对话 ==={RESET}")

    # 先确认 v3 服务可用
    try:
        r = requests.get(f"{BASE_URL}/v3/", timeout=5)
        check("v3 页面可访问", r.status_code == 200)
    except Exception as e:
        check("v3 页面可访问", False, str(e))
        return

    def ask(question: str) -> dict:
        r = requests.post(
            f"{BASE_URL}/v3/chat",
            json={"message": question},
            timeout=60,   # LLM 调用可能需要较长时间
        )
        return r.json()

    # Case 1: 数据库主从延迟 → 读取 sop-002
    data = ask("数据库主从延迟超过30秒怎么处理？")
    check("主从延迟：有 tool_calls 记录",
          len(data.get("tool_calls", [])) > 0,
          f"tool_calls: {data.get('tool_calls')}")
    check("主从延迟：sources 包含 sop-002",
          "sop-002" in data.get("sources", []),
          f"sources: {data.get('sources')}")
    check("主从延迟：reply 非空且有实质内容",
          len(data.get("reply", "")) > 50,
          f"reply 长度: {len(data.get('reply', ''))}")

    # Case 2: 服务 OOM → 读取 sop-001
    data = ask("服务 OOM 了怎么办？")
    check("OOM：sources 包含 sop-001",
          "sop-001" in data.get("sources", []),
          f"sources: {data.get('sources')}")
    check("OOM：tool_calls 包含 readFile",
          any(tc.get("tool") == "readFile" for tc in data.get("tool_calls", [])),
          f"tool_calls: {[tc.get('tool') for tc in data.get('tool_calls', [])]}")

    # Case 3: 怀疑入侵 → 读取 sop-005
    data = ask("怀疑有人入侵了系统")
    check("入侵：sources 包含 sop-005",
          "sop-005" in data.get("sources", []),
          f"sources: {data.get('sources')}")

    # Case 4: 推荐质量下降 → 读取 sop-008
    data = ask("推荐结果质量下降了")
    check("推荐质量：sources 包含 sop-008",
          "sop-008" in data.get("sources", []),
          f"sources: {data.get('sources')}")

    # Case 5: 工具调用格式校验
    data = ask("P0故障的响应流程是什么？")
    tool_calls = data.get("tool_calls", [])
    check("P0故障：tool_calls 格式正确（含tool/input/output/time_ms）",
          all(
              all(k in tc for k in ["tool", "input", "output", "time_ms"])
              for tc in tool_calls
          ),
          f"tool_calls keys: {[list(tc.keys()) for tc in tool_calls]}")
    check("P0故障：reply 非空",
          len(data.get("reply", "")) > 50,
          f"reply 长度: {len(data.get('reply', ''))}")

# ════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("On-Call 助手 - Golden Test 验收")
    print(f"{'='*50}")

    test_phase0()
    test_phase1()
    test_phase2()
    test_phase3()

    print(f"\n{'='*50}")
    print(f"结果：{GREEN}{passed} PASS{RESET}  {RED}{failed} FAIL{RESET}")
    print(f"{'='*50}\n")

    sys.exit(0 if failed == 0 else 1)