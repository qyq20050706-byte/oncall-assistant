"""
Golden Test 验收脚本
用法：python tests/validate.py
每个 Phase 完成后运行，全部 PASS 才进入下一 Phase
"""

import sys
import json
import requests

BASE_URL = "http://localhost:8000"

# ============================================================
# 颜色输出
# ============================================================
GREEN = "\033[92m"
RED = "\033[91m"
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
        print(f"{RED}❌ FAIL{RESET} {name}" + (f" — {detail}" if detail else ""))
        failed += 1

# ============================================================
# Phase 0 验收：服务可达 + 文档加载
# ============================================================
def test_phase0():
    print(f"\n{YELLOW}=== Phase 0 验收：服务启动 + 文档加载 ==={RESET}")
    
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        check("服务可达（GET /）", r.status_code == 200)
    except Exception as e:
        check("服务可达（GET /）", False, str(e))
        return

    # 验证 v1 页面可访问
    r = requests.get(f"{BASE_URL}/v1/", timeout=5)
    check("v1 页面可访问", r.status_code == 200)

# ============================================================
# Phase 1 验收：关键词搜索
# ============================================================
def test_phase1():
    print(f"\n{YELLOW}=== Phase 1 验收：关键词搜索 ==={RESET}")

    # Case 1: q=OOM → 应包含 sop-001
    r = requests.get(f"{BASE_URL}/v1/search?q=OOM", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=OOM 返回 sop-001", "sop-001" in ids, f"实际结果: {ids}")

    # Case 2: q=故障 → 应返回多个文档（>= 3）
    r = requests.get(f"{BASE_URL}/v1/search?q=%E6%95%85%E9%9A%9C", timeout=5)
    data = r.json()
    check("q=故障 返回多个文档(>=3)", len(data["results"]) >= 3,
          f"实际返回 {len(data['results'])} 个")

    # Case 3: q=replication → 应返回空（只在 script 里）
    r = requests.get(f"{BASE_URL}/v1/search?q=replication", timeout=5)
    data = r.json()
    check("q=replication 返回空", len(data["results"]) == 0,
          f"实际结果: {[res['id'] for res in data['results']]}")

    # Case 4: q=CDN → 应包含 sop-003 和 sop-010
    r = requests.get(f"{BASE_URL}/v1/search?q=CDN", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=CDN 包含 sop-003", "sop-003" in ids, f"实际结果: {ids}")
    check("q=CDN 包含 sop-010", "sop-010" in ids, f"实际结果: {ids}")

    # Case 5: q=& → 应返回含 & 字符的文档（sop-003, sop-010）
    # 注意：& 必须 URL 编码为 %26
    r = requests.get(f"{BASE_URL}/v1/search?q=%26", timeout=5)
    data = r.json()
    ids = [res["id"] for res in data["results"]]
    check("q=& 查询词正确解析", data["query"] == "&",
          f"实际解析到的 query: '{data['query']}'")
    check("q=& 返回 sop-003 或 sop-010",
          "sop-003" in ids or "sop-010" in ids,
          f"实际结果: {ids}")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print("On-Call 助手 - Golden Test 验收")
    print(f"{'='*50}")

    test_phase0()
    test_phase1()
    # test_phase2()  # Phase 2 完成后解注释
    # test_phase3()  # Phase 3 完成后解注释

    print(f"\n{'='*50}")
    print(f"结果：{GREEN}{passed} PASS{RESET}  {RED}{failed} FAIL{RESET}")
    print(f"{'='*50}\n")

    sys.exit(0 if failed == 0 else 1)