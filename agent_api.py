"""Minimal HTTP API for the city-renewal policy and case research agent.

Run: python agent_api.py --database cityrenewal_agent_v2.db
POST /search with {"query":"更新", "district":"丰台区"}
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _fts_query(query: str) -> str:
    return query.replace('"', ' ').replace('*', ' ').strip()


def _group_for(level: str, jurisdiction: str, tier: str, district: str) -> str:
    if tier != "direct_basis":
        return "待核验线索" if tier == "needs_verification" else "案例与经验参考"
    if level == "national":
        return "国家级依据"
    if jurisdiction == "北京市":
        return "北京市级依据"
    if district and jurisdiction == district:
        return "目标区依据"
    if jurisdiction.startswith("北京市"):
        return "北京其他区参考"
    return "外地政策参考"


def search(database: Path, query: str, district: str = "", limit: int = 8) -> dict:
    if not query.strip():
        return {"query": query, "district": district, "groups": {}, "message": "请输入政策问题或关键词。"}
    con = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    term = _fts_query(query)
    try:
        documents = con.execute(
            """SELECT d.title,d.document_type,d.evidence_tier,d.jurisdiction_level,d.jurisdiction_name,
                       d.issuing_authority,d.document_number,d.published_date,d.effective_date,
                       d.validity_status,d.official_url,d.original_path,
                       snippet(documents_fts,2,'<mark>','</mark>',' … ',32) excerpt
                FROM documents_fts JOIN documents d ON d.rowid=documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY CASE WHEN d.jurisdiction_name=? THEN 0
                              WHEN d.jurisdiction_level='national' THEN 1
                              WHEN d.jurisdiction_name='北京市' THEN 2
                              WHEN d.jurisdiction_name LIKE '北京市%' THEN 3 ELSE 4 END,
                         bm25(documents_fts)
                LIMIT ?""",
            (term, district or "__none__", limit * 3),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        return {"query": query, "district": district, "groups": {}, "message": f"无法解析检索词：{exc}"}
    groups: dict[str, list[dict]] = {}
    for row in documents:
        item = dict(row)
        group = _group_for(item.pop("jurisdiction_level"), item["jurisdiction_name"], item["evidence_tier"], district)
        groups.setdefault(group, []).append(item)

    web = con.execute(
        """SELECT w.title,w.jurisdiction_name,w.record_type,w.evidence_tier,w.published_date,w.url,
                       snippet(web_records_fts,1,'<mark>','</mark>',' … ',24) excerpt
                FROM web_records_fts JOIN web_records w ON w.id=web_records_fts.rowid
                WHERE web_records_fts MATCH ? ORDER BY bm25(web_records_fts) LIMIT ?""",
        (term, limit),
    ).fetchall()
    if web:
        groups["动态与案例线索"] = [dict(row) for row in web]
    con.close()
    return {
        "query": query,
        "district": district,
        "groups": groups,
        "message": None if groups else "当前库未命中；请补充关键词或从官方渠道继续核验。",
        "disclaimer": "结果按地域和证据等级分层呈现，不构成自动合规结论。",
    }


class Handler(BaseHTTPRequestHandler):
    database: Path

    def _html(self) -> bytes:
        return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>城市更新政策检索</title>
<style>body{font:16px system-ui;max-width:920px;margin:40px auto;padding:0 20px;color:#222}input,button{font:inherit;padding:10px;margin:4px}input{width:38%}button{cursor:pointer}section{margin:20px 0;padding:16px;border:1px solid #ddd;border-radius:8px}h2{margin-top:0}a{word-break:break-all}small{color:#666}</style>
<h1>城市更新政策与案例检索</h1><p>输入问题和目标行政区；结果不构成自动合规结论。</p>
<input id="q" placeholder="例如：联合审查、老旧小区、房票制度"><input id="d" placeholder="例如：北京市丰台区"><button onclick="go()">搜索</button><div id="out"></div>
<script>async function go(){const out=document.getElementById('out');out.textContent='正在检索…';try{const r=await fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q.value,district:d.value})});const x=await r.json();if(!r.ok)throw Error(x.message||'请求失败');out.innerHTML='';if(x.message){out.innerHTML='<p>'+x.message+'</p>';return}for(const [name,items] of Object.entries(x.groups)){const s=document.createElement('section');s.innerHTML='<h2>'+name+'</h2>';for(const i of items){const p=document.createElement('div');p.innerHTML='<b>'+i.title+'</b><br><small>'+[i.jurisdiction_name,i.published_date,i.evidence_tier].filter(Boolean).join(' · ')+'</small><p>'+ (i.excerpt||'') +'</p>'+(i.official_url?'<a href="'+i.official_url+'" target="_blank">官方链接</a>':i.url?'<a href="'+i.url+'" target="_blank">原始网页</a>':'');s.appendChild(p)}out.appendChild(s)}}catch(e){out.innerHTML='<p>检索失败：'+e.message+'</p>'}}</script>'''.encode("utf-8")

    def _json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json({"status": "ok", "database": self.database.name})
        elif self.path == "/":
            body = self._html()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"message": "Use GET /health or POST /search."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/search":
            self._json({"message": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            self._json(search(self.database, str(payload.get("query", "")), str(payload.get("district", ""))))
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"message": f"Invalid JSON request: {exc}"}, HTTPStatus.BAD_REQUEST)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("cityrenewal_agent_v2.db"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    Handler.database = args.database
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Agent API: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
