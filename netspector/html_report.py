"""Self-contained, offline HTML reports with escaped source data."""
import base64
import hashlib
from html import escape
import json

from . import __version__

STYLE = '''
:root{color-scheme:light;--ink:#142d3b;--muted:#536875;--line:#dce5e9;--paper:#f5f8fa;--accent:#087f73}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
header{background:#112e3d;color:white;padding:42px max(24px,calc((100vw - 1200px)/2));border-bottom:5px solid #41c8af}
header .brand{color:#8ae0ce;font-size:13px;font-weight:700;letter-spacing:.15em}h1{font-size:clamp(28px,4vw,40px);letter-spacing:-.04em;margin:8px 0}header p{color:#c2d2db;margin:0;max-width:760px}
main{max-width:1248px;margin:auto;padding:28px 24px 56px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.metric{background:white;border:1px solid var(--line);border-radius:12px;padding:16px 20px}.metric strong{display:block;font-size:29px;line-height:1.3}.metric span{color:var(--muted);font-size:13px}
.toolbar{display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin:26px 0}.toolbar label{display:block;font-size:12px;font-weight:700;color:var(--muted)}input,select{font:inherit;border:1px solid #afc1cb;border-radius:7px;background:white;color:var(--ink);padding:10px 12px;margin-top:5px}input{width:min(440px,80vw)}select{min-width:150px}input:focus,select:focus{outline:3px solid #91d6ca;outline-offset:1px}.toolbar p{margin:0 0 10px;color:var(--muted);font-size:13px}
section{margin-top:30px}h2{font-size:20px;letter-spacing:-.025em;margin:0 0 12px}.section-note{color:var(--muted);margin:-4px 0 15px;font-size:13px}.connection{background:white;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:10px;padding:18px 20px;margin:12px 0}.connection-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.namespace{font-size:12px;color:var(--muted)}.path{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:15px 0}.node{border:1px solid var(--line);background:#f8fbfc;border-radius:8px;padding:9px 12px;max-width:100%;overflow-wrap:anywhere}.node small{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}.node b{font-weight:600}.node .detail{font-size:12px;color:#365763}.arrow{color:var(--accent)}.reason{color:#8a5b20;font-size:13px;margin:7px 0}
.badge{display:inline-block;border-radius:5px;padding:2px 8px;background:#e6f5f0;color:#126551;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}.badge.warn{color:#805514;background:#fff2d8}.badge.neutral{color:#425b6a;background:#eaf0f4}
.table-wrap{background:white;border:1px solid var(--line);border-radius:10px;overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;background:#edf3f6;color:#4f6775;font-size:11px;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}th,td{padding:13px 15px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}td.target{min-width:230px;max-width:440px;overflow-wrap:anywhere}td.source{min-width:200px;max-width:330px;overflow-wrap:anywhere}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}details{margin-top:7px}summary{cursor:pointer;color:var(--accent);font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;background:#f1f6f8;padding:10px;border-radius:6px;max-width:650px}.empty{padding:22px;color:var(--muted);border:1px dashed #bdced7;border-radius:8px}.diagnostic{padding:12px 16px;background:#fff4df;border-radius:7px;margin:8px 0;overflow-wrap:anywhere}footer{margin-top:35px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}[hidden]{display:none!important}
@media(max-width:650px){.metrics{grid-template-columns:repeat(2,1fr)}main{padding:20px 16px}.toolbar{gap:10px}header{padding:30px 20px}.connection{padding:15px}.node{flex:1 1 160px}.arrow{display:none}}
@media print{header{background:white;color:#142d3b;border-bottom:2px solid #087f73}header p{color:#536875}.toolbar{display:none}main{max-width:none;padding:16px 0}.connection{break-inside:avoid}.table-wrap{overflow:visible}body{background:white}}
'''
SCRIPT = '''
const search = document.getElementById('search');
const direction = document.getElementById('direction');
function filterReport() {
  const query = search.value.toLocaleLowerCase();
  const selected = direction.value;
  let visible = 0;
  document.querySelectorAll('[data-record]').forEach(row => {
    row.hidden = Boolean((selected && row.dataset.direction !== selected) || !row.textContent.toLocaleLowerCase().includes(query));
    if (!row.hidden) visible++;
  });
  document.getElementById('visible-count').textContent = visible + ' matching records';
  ['connections', 'findings'].forEach(id => {
    const section = document.getElementById(id);
    const any = Array.from(section.querySelectorAll('[data-record]')).some(row => !row.hidden);
    section.querySelector('.empty').hidden = any;
  });
}
search.addEventListener('input', filterReport);
direction.addEventListener('change', filterReport);
filterReport();
'''


def text(value):
    return escape(str(value if value is not None else '—'), quote=True)


def badge(status):
    tone = 'warn' if status in {'unresolved', 'candidate', 'partial'} else 'neutral' if status == 'inferred' else ''
    return f'<span class="badge {tone}">{text(status)}</span>'


def details(label, value):
    return f'<details><summary>{text(label)}</summary><pre>{text(json.dumps(value, indent=2, ensure_ascii=False))}</pre></details>' if value else ''


def render_html(report):
    findings = report['findings']
    connections = report.get('connections', [])
    diagnostics = report['diagnostics']
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    cards = []
    for connection in connections:
        nodes = []
        for node in connection['nodes']:
            label = str(node['name']) + (f":{node['port']}" if node.get('port') is not None else '')
            extra = (f"{node['host']}{node.get('path', '')}" if node.get('host') is not None else node.get('protocol', ''))
            nodes.append(f'<div class="node"><small>{text(node["kind"])}</small><b>{text(label)}</b><div class="detail">{text(extra)}</div></div>')
        reasons = f'<p class="reason">{text(", ".join(connection["reasons"]))}</p>' if connection['reasons'] else ''
        proof = details('Source evidence', connection['evidence'])
        cards.append(f'<article class="connection" data-record="connection" data-direction="inbound"><div class="connection-head"><span class="namespace">Namespace · {text(connection["namespace"])}</span>{badge(connection["status"])}</div><div class="path">' + '<span class="arrow" aria-hidden="true">→</span>'.join(nodes) + f'</div>{reasons}{proof}</article>')
    rows = []
    for finding in findings:
        target = f'<code>{text(finding["target"])}</code>'
        target += details('Candidate targets', finding.get('candidates'))
        location = f'{finding["file"]}:{finding["line"] if finding["line"] is not None else "—"}'
        proof = details('Evidence and reference', dict(reference=finding.get('reference'), evidence=finding.get('evidence', [])))
        rows.append(f'<tr data-record="finding" data-direction="{text(finding["direction"])}"><td>{text(finding["direction"])}</td><td>{text(finding["kind"])}</td><td class="target">{target}</td><td>{text(finding.get("port"))}</td><td>{badge(finding["status"])}</td><td class="source"><code>{text(location)}</code>{proof}</td></tr>')
    counts = [('Findings', len(findings)), ('Network paths', len(connections)), ('Paths needing review', sum(c['status'] != 'declared' for c in connections)), ('Diagnostics', len(diagnostics))]
    metrics = ''.join(f'<div class="metric"><strong>{count}</strong><span>{label}</span></div>' for label, count in counts)
    errors = ''.join(f'<div class="diagnostic"><b>{text(d["file"])}</b> · {text(d["message"])}</div>' for d in diagnostics)
    if not errors:
        errors = '<p class="section-note">No parsing diagnostics.</p>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>netspector · Network report</title><style>{STYLE}</style></head><body>
<header><div class="brand">netspector / network inventory</div><h1>Follow the declared connections.</h1><p>Source and configuration evidence in one view. These paths describe declarations, not observed traffic or verified reachability.</p></header>
<main><div class="metrics">{metrics}</div>
<div class="toolbar"><label>Search records<input id="search" type="search" placeholder="Host, service, file or namespace…"></label><label>Direction<select id="direction"><option value="">All directions</option><option value="inbound">Inbound</option><option value="outbound">Outbound</option><option value="unknown">Unknown</option></select></label><p id="visible-count" role="status" aria-live="polite"></p></div>
<noscript><p>All records are shown. Enable JavaScript to use local search and filters.</p></noscript>
<section id="connections"><h2>Kubernetes network paths</h2><p class="section-note">Ingress → Service → selected workload → declared container port. Missing references remain visible.</p>{''.join(cards)}<p class="empty" {'hidden' if cards else ''}>No matching network paths.</p></section>
<section id="findings"><h2>Discovered endpoints</h2><div class="table-wrap"><table><thead><tr><th>Direction</th><th>Kind</th><th>Target</th><th>Port</th><th>Status</th><th>Source</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p class="empty" {'hidden' if rows else ''}>No matching findings.</p></section>
<section><h2>Scan diagnostics</h2>{errors}</section>
<footer>netspector {text(__version__)} · Offline report · Search runs locally · No external assets or endpoint requests.<br>Missing namespace defaults to “default”. Kubernetes declarations are not matched to Python applications automatically.</footer></main><script>{SCRIPT}</script></body></html>\n'''
