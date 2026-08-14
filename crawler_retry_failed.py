"""针对失败信源的增强测试脚本
- 添加完整浏览器 headers
- 请求延迟增加到 25 秒
- 仅测试之前失败的 9 个信源
"""
import argparse
import sys
import time
from pathlib import Path

# 添加 headers 模拟浏览器
ENHANCED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    # 部分站点需要这些
    "DNT": "1",
}

# 之前失败的 9 个信源 ID
FAILED_SOURCE_IDS = [
    "govcn",       # 国务院政策文件库 - 403 Forbidden
    "scio",        # 国务院新闻办 - SSL 证书错误
    "cs-zjw",      # 长沙市住建局 - SSL 证书不匹配
    "sz-pnr",      # 深圳规划自然资源局 - 412
    "sz-portal",   # 深圳市人民政府 - SSL 错误
    "cd-zjw",      # 成都市住建局 - 412
    "gs-zjw",      # 甘肃省住建厅 - 412
    "cdb",         # 国家开发银行 - 412
    "cpppc",       # 财政部PPP中心 - 403
]


def main():
    # 导入原模块
    sys.path.insert(0, str(Path(__file__).parent))
    import crawler_standalone as cw

    # 禁用 SSL 验证（解决部分证书问题）
    import requests
    requests.packages.urllib3.disable_warnings()
    import urllib3
    urllib3.disable_warnings()

    print("=" * 60)
    print("增强测试：失败信源重试（25秒延迟 + 完整 headers）")
    print("=" * 60)
    print(f"信源数量: {len(FAILED_SOURCE_IDS)}")
    print(f"请求延迟: 25 秒")
    print(f"Headers: 完整浏览器模拟")
    print("=" * 60)

    # 修改全局 session 的 headers
    original_fetch = cw.fetch_html

    def enhanced_fetch(session, url, timeout=10, retries=2, retry_delay=2):
        """增强版 fetch，使用完整 headers"""
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = session.get(url, timeout=timeout, headers=ENHANCED_HEADERS)
                resp.raise_for_status()
                return cw.decode_html(resp.content)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        raise cw.FetchError(f"GET {url} 失败（尝试 {retries + 1} 次）：{last_error}")

    # 替换 fetch 函数
    cw.fetch_html = enhanced_fetch

    # 创建 session（禁用 SSL 验证）
    session = requests.Session()
    session.verify = False  # 禁用 SSL 验证
    session.headers.update(ENHANCED_HEADERS)

    # 重新定义 session maker
    original_make_session = cw._make_session

    def make_session_with_ssl_off(proxy=None):
        s = requests.Session()
        s.verify = False  # 禁用 SSL 验证
        s.headers.update(ENHANCED_HEADERS)
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        return s

    cw._make_session = make_session_with_ssl_off

    # 运行探测
    results = []
    for i, source_id in enumerate(FAILED_SOURCE_IDS, 1):
        print(f"\n[{i}/{len(FAILED_SOURCE_IDS)}] 探测 {source_id}...")
        result = cw.probe(source_id, timeout=10, retries=2, limit=5)
        results.append(result)

        if result["ok"]:
            print(f"  ✓ 成功！HTML: {result['html_len']} 字节, 记录: {len(result['records'])} 条")
            for r in result["records"][:3]:
                print(f"    - {r.title[:50]}...")
        else:
            print(f"  ✗ 失败: {result['error']}")

        # 延迟 25 秒
        if i < len(FAILED_SOURCE_IDS):
            print(f"  等待 25 秒...")
            time.sleep(25)

    # 统计
    success = sum(1 for r in results if r["ok"])
    print("\n" + "=" * 60)
    print(f"测试完成: {success}/{len(FAILED_SOURCE_IDS)} 成功")
    print("=" * 60)

    # 恢复原函数
    cw.fetch_html = original_fetch
    cw._make_session = original_make_session


if __name__ == "__main__":
    main()
