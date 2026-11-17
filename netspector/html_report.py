"""Self-contained, offline HTML reports with escaped source data."""
import base64
import hashlib
from html import escape
import json

from . import __version__
from .network_graph import build_graph
from pathlib import PurePosixPath

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
STYLE += '''
header{padding:20px max(24px,calc((100vw - 1320px)/2));border-bottom-width:3px}header .brand{font-size:11px}h1{font-size:26px;margin:3px 0}h1 span{font-weight:400;color:#a6c5ce;font-size:19px}header p{font-size:12px}main{max-width:1368px;padding-top:18px}.metrics{gap:10px}.metric{padding:10px 16px;display:flex;align-items:baseline;gap:10px}.metric strong{font-size:24px}.toolbar{margin:16px 0;gap:12px}input,select{padding:7px 10px;font-size:13px}input{width:min(300px,75vw)}section{margin-top:16px}.map-section{background:white;border:1px solid var(--line);border-radius:12px;overflow:hidden}.map-heading{display:flex;align-items:center;justify-content:space-between;padding:16px 20px 0}.map-heading h2{margin-bottom:4px}.map-heading .section-note{margin:0}.zoom{display:flex;gap:5px}button{cursor:pointer;background:#f4f8fa;border:1px solid #cbd9df;color:var(--ink);border-radius:5px;padding:5px 12px}.map-layout{display:grid;grid-template-columns:minmax(0,1fr) 270px;margin-top:8px}.graph-scroll{overflow:auto;max-height:620px;background:radial-gradient(#dbe5e9 .75px,transparent .75px);background-size:16px 16px}#network-svg{display:block;width:100%;max-height:none}#selection{border-left:1px solid var(--line);padding:18px;font-size:12px;overflow:auto;max-height:620px;overflow-wrap:anywhere;background:#fafcfd}#selection h3{font-size:16px;margin:0 0 6px}#selection ul{padding-left:16px}#selection li{margin-bottom:8px}#selection pre{font-size:10px}.legend{display:flex;flex-wrap:wrap;gap:20px;font-size:11px;padding:10px 20px;border-top:1px solid var(--line);color:var(--muted)}.map-section>.section-note{padding:0 20px;margin:0 0 12px;font-size:11px}.graph-node,.graph-edge{cursor:pointer;outline:none}.graph-node rect{fill:#fff;stroke:#c5d6dc;stroke-width:1.4}.app-node rect{fill:#113d4a;stroke:#113d4a}.host-node rect{fill:#eef9f5;stroke:#9dcbbb}.node-name{font:600 12px system-ui;fill:#193f4c}.node-kind{font:10px system-ui;fill:#617b85}.app-node .node-name{fill:white}.app-node .node-kind{fill:#b5d7d9}.graph-node:hover rect,.graph-node:focus rect,.graph-node.selected rect{stroke:#eaa43c;stroke-width:3}.edge-line{stroke-linejoin:round;fill:none;stroke:#218c7c;stroke-width:1.7}.edge-hit{fill:none;stroke:transparent;stroke-width:14}.uncertain .edge-line{stroke:#a07b35;stroke-dasharray:5 4}.graph-edge:hover .edge-line,.graph-edge:focus .edge-line,.graph-edge.selected .edge-line{stroke:#da8b1d;stroke-width:3}.inventory{background:white;border:1px solid var(--line);border-radius:9px;margin-top:12px;padding:12px 16px}.inventory>summary{font-size:13px;font-weight:600;color:var(--ink)}.inventory section{margin-top:12px}th,td{padding:9px 12px}footer{margin-top:20px;padding-top:12px}.connection{padding:10px 12px;margin:8px 0}.path{margin:8px 0}.node{padding:6px 9px}
@media(max-width:900px){.map-layout{grid-template-columns:1fr}#selection{border-left:0;border-top:1px solid var(--line);max-height:240px}.graph-scroll{max-height:480px}.metric{display:block}.metric strong{font-size:22px}}@media(max-width:650px){header{padding:18px 16px}main{padding:14px 12px}.toolbar{align-items:stretch}.toolbar label{flex:1}.toolbar input,.toolbar select{width:100%;min-width:0}.map-heading{padding:12px}h1{font-size:22px}h1 span{display:block;font-size:15px}.legend{gap:10px;padding:10px 12px}#network-svg{min-width:620px}}
@media print{.map-layout{display:block}#selection,.zoom{display:none}.graph-scroll{max-height:none;overflow:visible}.inventory:not([open]){display:none}}
'''
STYLE += '''
.project-zone>rect{fill:#f3f7fc;stroke:#b5c8df;stroke-width:1.3;stroke-dasharray:6 4}.host-zone>rect{fill:#f1f8f5;stroke:#b1cfc1;stroke-width:1.3}.zone-title{font:700 13px system-ui;fill:#345477}.zone-subtitle{font:10px system-ui;fill:#6b8198}.graph-node .node-hit{fill:transparent;stroke:transparent}.graph-node:hover .node-hit,.graph-node:focus .node-hit,.graph-node.selected .node-hit{fill:#ffffffbb;stroke:#5f91cc;stroke-width:1.5}.device-icon{fill:#e4ecf6;stroke:#6689b5;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}.device-icon rect{fill:#e4ecf6;stroke:#6689b5;stroke-width:1.7}.device-icon .device-light{fill:#40bca2;stroke:none}.app-node .device-icon rect{fill:#d4e5fa;stroke:#497db9}.host-node .device-icon rect{fill:#dbeee6;stroke:#5a9680}.host-globe{fill:#e8f8f2;stroke:#5a9680}.graph-node .node-name,.app-node .node-name{fill:#203c59;font-size:12px}.graph-node .node-kind,.app-node .node-kind{fill:#637b92;font-size:10px}.icon-question{fill:#637b92;stroke:none;font:700 24px system-ui}.edge-line{stroke:#6784a2;stroke-width:1.6}.edge-caption{font:10px system-ui;fill:#3b5876;paint-order:stroke;stroke:white;stroke-width:4px;stroke-linejoin:round;pointer-events:none}.graph-scroll{background:white;max-height:760px}#network-svg{touch-action:none}.zoom{flex-wrap:wrap;justify-content:flex-end}.map-layout{grid-template-columns:minmax(0,1fr) 230px}.graph-node{cursor:grab}.graph-node:active{cursor:grabbing}@media(max-width:900px){.map-layout{grid-template-columns:1fr}}@media(max-width:650px){.map-heading{align-items:flex-start;gap:10px}.zoom{max-width:170px}.zoom button{padding:5px 7px;font-size:11px}}
'''
SCRIPT = '''
const graph = JSON.parse(document.getElementById('graph-data').textContent);
const canvas = document.getElementById('network-svg');
const groupSelect = document.getElementById('project');
const search = document.getElementById('search');
const direction = document.getElementById('direction');
const ns = 'http://www.w3.org/2000/svg';
let selected = null;
let scale = 1;
const manualPositions = new Map();
let dragState = null;
let dragged = false;
function positionKey(id) { return groupSelect.value + ':' + id; }
function diagramIcon(parent, kind) {
  const icon = svg('g', {'class':'device-icon',transform:'translate(-25,-37)'}, parent);
  const path = d => svg('path', {d}, icon);
  if (kind === 'Ingress') {
    path('M 4 38 V 12 L 25 2 L 46 12 V 38 L 25 48 Z M 25 2 V 48 M 4 12 L 25 23 L 46 12');
    path('M 12 28 H 38 M 32 22 L 38 28 L 32 34');
  } else if (kind === 'Service') {
    svg('rect',{x:0,y:14,width:50,height:25,rx:4},icon);
    for(let x=7;x<45;x+=9) svg('rect',{x,y:23,width:5,height:7,rx:1},icon);
    path('M 12 7 H 38 M 33 3 L 38 7 L 33 11 M 38 45 H 12 M 17 41 L 12 45 L 17 49');
  } else if (kind === 'Container') {
    path('M 3 13 L 25 3 L 47 13 V 38 L 25 49 L 3 38 Z M 3 13 L 25 24 L 47 13 M 25 24 V 49 M 14 8 L 36 19');
  } else if (kind === 'Unresolved') {
    path('M 8 39 C -4 37 -2 20 10 19 C 8 0 39 -1 40 18 C 56 18 57 39 43 39 Z');
    label(icon,'?',{x:25,y:30,'text-anchor':'middle','class':'icon-question'});
  } else {
    for(let y=2;y<43;y+=14) {
      svg('rect',{x:5,y,width:40,height:12,rx:2},icon);
      svg('circle',{cx:12,cy:y+6,r:2,'class':'device-light'},icon);
      path(`M 22 ${y+4} H 38 M 22 ${y+8} H 38`);
    }
    if(kind === 'Application') path('M 12 49 H 38 M 25 42 V 49');
    if(kind === 'Host') {svg('circle',{cx:44,cy:42,r:9,'class':'host-globe'},icon);path('M 35 42 H 53 M 44 33 C 39 36 39 48 44 51 C 49 48 49 36 44 33');}
  }
}
function edgeCaption(edge) {
  const ports = new Set(), protocols = new Set();
  const target = graph.nodes.find(n => n.id === edge.target);
  edge.records.forEach(raw => {
    const record = raw.finding || raw;
    if(record.nodes) {
      record.nodes.filter(n => n.kind === target.kind && n.name === target.label).forEach(n => {if(n.port)ports.add(String(n.port));if(n.protocol)protocols.add(n.protocol.toUpperCase());});
    } else {
      try {
        const url = new URL(raw.candidate?.target || record.target);
        protocols.add(url.protocol.slice(0,-1).toUpperCase());
        const port=url.port || ({'https:':'443','http:':'80'}[url.protocol]);
        if(port)ports.add(port);
      } catch {if(record.port)ports.add(String(record.port));if(record.protocol)protocols.add(record.protocol.toUpperCase());}
    }
  });
  const values = [...ports].sort((a,b)=>Number(a)-Number(b));
  const parts = [[...protocols].sort().join('/'),values.slice(0,3).join(',')+(values.length>3?' +'+(values.length-3):'')].filter(Boolean);
  return parts.join(' · ') || (edge.relation === 'association' ? 'configuration' : 'declared');
}

function svg(tag, attrs, parent = canvas) {
  const element = document.createElementNS(ns, tag);
  Object.entries(attrs).forEach(([key,value]) => element.setAttribute(key, value));
  parent.appendChild(element);
  return element;
}
function label(parent, value, attrs) {
  const element = svg('text', attrs, parent);
  element.textContent = value;
  return element;
}
function proofText(record) { return JSON.stringify(record).toLocaleLowerCase(); }
function showDetails(value, type) {
  selected = value.id;
  if (groupSelect.value) {
    function recordGroup(file) {
      return graph.projects.filter(p => p === '.' || file.startsWith(p + '/')).sort((a,b) => b.length-a.length)[0] || '.';
    }
    value = {...value, records:value.records.filter(r => {
      const record = r.finding || r;
      return record.file ? recordGroup(record.file) === groupSelect.value : (record.nodes || []).some(n => recordGroup(n.file || '') === groupSelect.value);
    })};
  }
  const panel = document.getElementById('selection');
  panel.replaceChildren();
  const title = document.createElement('h3');
  const source = graph.nodes.find(n => n.id === value.source);
  const target = graph.nodes.find(n => n.id === value.target);
  title.textContent = type === 'node' ? value.label : source.label + (value.relation === 'association' ? ' ··· ' : ' → ') + target.label;
  panel.appendChild(title);
  const hint = document.createElement('p');
  hint.className = 'section-note';
  hint.textContent = type === 'node' ? value.kind + ' · ' + value.records.length + ' distinct source records' :
    (value.relation === 'association' ? 'Configuration association; direction unknown' : 'Declared direction; not observed traffic') + ' · ' + value.records.length + ' source records';
  panel.appendChild(hint);
  const summary = document.createElement('ul');
  const lines = new Set();
  value.records.forEach(record => {
    const finding = record.finding || record;
    if (finding.target) lines.add((finding.direction || 'unknown') + ' · ' + (record.candidate?.target || finding.target) + (finding.port ? ' · port ' + finding.port : ''));
    if (finding.nodes) finding.nodes.forEach(n => lines.add(n.kind + '/' + n.name + (n.port ? ':' + n.port : '') + (n.host ? ' · ' + n.host + (n.path || '') : '')));
  });
  [...lines].sort().forEach(line => { const li = document.createElement('li'); li.textContent = line; summary.appendChild(li); });
  panel.appendChild(summary);
  const details = document.createElement('details');
  const heading = document.createElement('summary');
  heading.textContent = 'All source evidence (' + value.records.length + ')';
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(value.records, null, 2);
  details.append(heading, pre);
  panel.appendChild(details);
  document.querySelectorAll('.graph-node,.graph-edge').forEach(n => n.classList.toggle('selected', n.dataset.id === selected));
}
function drawGraph() {
  const project = groupSelect.value;
  const query = search.value.toLocaleLowerCase().trim();
  const chosenDirection = direction.value;
  let edges = graph.edges.filter(e => !project || e.projects.includes(project));
  const neighbors = new Set(edges.flatMap(e => [e.source, e.target]));
  let nodes = graph.nodes.filter(n => !project || n.projects.includes(project) || neighbors.has(n.id));
  if (chosenDirection) {
    edges = edges.filter(e => e.records.some(r => (r.finding || r).direction === chosenDirection));
    if (chosenDirection === 'unknown') edges = edges.map(e => ({...e, relation:'association', uncertain:true}));
    const related = new Set(edges.flatMap(e => [e.source, e.target]));
    nodes = nodes.filter(n => related.has(n.id) || n.records.some(r => (r.finding || r).direction === chosenDirection));
  }
  if (query) {
    const matches = new Set(nodes.filter(n => n.label.toLocaleLowerCase().includes(query)).map(n => n.id));
    edges = edges.filter(e => matches.has(e.source) || matches.has(e.target) || e.records.some(r => proofText(r).includes(query)));
    const context = new Set(edges.flatMap(e => [e.source,e.target]));
    nodes = nodes.filter(n => matches.has(n.id) || context.has(n.id) || (!edges.length && n.records.some(r => proofText(r).includes(query))));
  }
  // Render a bounded overview; keep all records below and allow project/search refinement.
  const total = nodes.length;
  nodes = nodes.slice(0, 160);
  const visible = new Set(nodes.map(n => n.id));
  edges = edges.filter(e => visible.has(e.source) && visible.has(e.target));
  const note = document.getElementById('graph-count');
  note.textContent = nodes.length + (total > nodes.length ? ' of ' + total : '') + ' nodes · ' + edges.length + ' connections' + (total > nodes.length ? ' · Refine project or search to see other nodes.' : '');
  canvas.replaceChildren();
  const defs = svg('defs', {});
  ['flow','maybe'].forEach(id => {
    const marker = svg('marker', {id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'}, defs);
    svg('path', {d:'M 0 0 L 10 5 L 0 10 z',fill:id === 'flow' ? '#218c7c' : '#a07b35'}, marker);
  });
  const position = new Map(), bounds = new Map();
  const projects = [...new Set(nodes.filter(n => n.kind !== 'Host').flatMap(n => n.projects))].sort();
  const width = 1320;
  const projectRows = new Map();
  function column(n) {return n.kind === 'Ingress' ? 0 : n.kind === 'Service' ? 1 : n.kind === 'Container' ? 3 : 2;}
  let cursor = 70;
  projects.forEach(project => {
    const members = nodes.filter(n => n.kind !== 'Host' && n.projects[0] === project);
    if(!members.length)return;
    const rows = Math.max(1,...[0,1,2,3].map(col => members.filter(n => column(n) === col).length));
    const height = Math.max(230,rows*135+95);
    projectRows.set(project,{top:cursor,height});
    cursor += height + 22;
  });
  const hosts = nodes.filter(n => n.kind === 'Host');
  const height = Math.max(420,cursor+35,hosts.length*135+140);
  canvas.setAttribute('viewBox', `0 0 ${width} ${height}`);
  canvas.style.width = scale * 100 + '%';
  canvas.style.minHeight = Math.min(800,height) + 'px';
  projectRows.forEach(({top,height:zoneHeight}, project) => {
    const zone = svg('g',{'class':'project-zone'});
    svg('rect',{x:20,y:top,width:1000,height:zoneHeight,rx:14},zone);
    label(zone,project === '.' ? graph.title : project,{x:40,y:top+28,'class':'zone-title'});
    label(zone,'PROJECT / APPLICATION',{x:40,y:top+45,'class':'zone-subtitle'});
    const members=nodes.filter(n=>n.kind!=='Host'&&n.projects[0]===project);
    [0,1,2,3].forEach(col=>{
      const items=members.filter(n=>column(n)===col);
      items.forEach((n,index)=>{
        position.set(n.id,{x:140+col*250,y:top+112+index*135});
        bounds.set(n.id,{left:100,right:940,top:top+95,bottom:top+zoneHeight-65});
      });
    });
  });
  const hostZone=svg('g',{'class':'host-zone'});
  svg('rect',{x:1050,y:70,width:250,height:height-105,rx:14},hostZone);
  label(hostZone,'SHARED HOSTS',{x:1070,y:98,'class':'zone-title'});
  label(hostZone,'One identity · all directions',{x:1070,y:117,'class':'zone-subtitle'});
  hosts.forEach((n,index)=>{
    position.set(n.id,{x:1175,y:175+index*135});
    bounds.set(n.id,{left:1140,right:1210,top:165,bottom:height-100});
  });
  nodes.forEach(n=>{
    const manual=manualPositions.get(positionKey(n.id)),limit=bounds.get(n.id);
    if(manual&&limit)position.set(n.id,{x:Math.max(limit.left,Math.min(limit.right,manual.x)),y:Math.max(limit.top,Math.min(limit.bottom,manual.y))});
  });
  const routeLanes = new Map();
  edges.forEach((e, edgeIndex) => {
    const a = position.get(e.source), b = position.get(e.target);
    const backwards = a.x > b.x;
    const sameColumn = a.x === b.x;
    const x1 = a.x + (backwards ? -38 : 38), x2 = b.x + (backwards ? 38 : -38);
    function portOffset(id) {
      const incident=edges.filter(edge=>edge.source===id||edge.target===id);
      return (incident.findIndex(edge=>edge.id===e.id)-(incident.length-1)/2)*Math.min(7,24/incident.length);
    }
    const ay=a.y-14+portOffset(e.source),by=b.y-14+portOffset(e.target);
    const span=Math.abs(a.x-b.x);
    const detour=backwards||span>350||sameColumn;
    const sourceNode=nodes.find(n=>n.id===e.source);
    const zone=projectRows.get(sourceNode.projects[0]);
    const laneKey=backwards||!zone?'global':sourceNode.projects[0];
    const laneIndex=routeLanes.get(laneKey)||0;
    if(detour)routeLanes.set(laneKey,laneIndex+1);
    const lane=backwards||!zone?24+(laneIndex%6)*18:zone.top+64+(laneIndex%6)*20;
    const offset=backwards?-25:25;
    const mid=(x1+x2)/2;
    const d=detour?`M ${x1} ${ay} H ${x1+offset} V ${lane} H ${x2-offset} V ${by} H ${x2}`:
      `M ${x1} ${ay} H ${mid} V ${by} H ${x2}`;
    const uncertain = e.uncertain || e.relation === 'association';
    const g = svg('g', {'class':'graph-edge' + (uncertain ? ' uncertain' : ''),'data-id':e.id,tabindex:0,role:'button','aria-label':graph.nodes.find(n=>n.id===e.source).label+' to '+graph.nodes.find(n=>n.id===e.target).label});
    svg('path', {d,'class':'edge-hit'}, g);
    const line = svg('path', {d,'class':'edge-line'}, g);
    if (e.relation !== 'association') line.setAttribute('marker-end', 'url(#' + (uncertain ? 'maybe' : 'flow') + ')');
    const caption=label(g,edgeCaption(e),{x:detour?(x1+x2)/2:mid,y:detour?lane-5:Math.min(ay,by)-8,'text-anchor':'middle','class':'edge-caption'});
    const title = svg('title', {}, g); title.textContent = e.records.length + ' source records; select for ports, paths and evidence';
    g.addEventListener('click', () => showDetails(e, 'edge'));
    g.addEventListener('keydown', event => { if(event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showDetails(e,'edge'); } });
  });
  nodes.forEach(n => {
    const p=position.get(n.id);
    if(!p)return;
    const g=svg('g',{'class':'graph-node '+(n.kind==='Host'?'host-node':n.kind==='Application'?'app-node':''),'data-id':n.id,transform:`translate(${p.x},${p.y})`,tabindex:0,role:'button','aria-label':n.kind+' '+n.label});
    svg('rect',{x:-94,y:-52,width:188,height:116,rx:12,'class':'node-hit'},g);
    diagramIcon(g,n.kind);
    label(g,n.label.length>27?n.label.slice(0,25)+'…':n.label,{x:0,y:34,'text-anchor':'middle','class':'node-name'});
    label(g,n.kind+(n.namespace?' · '+n.namespace:''),{x:0,y:51,'text-anchor':'middle','class':'node-kind'});
    const title=svg('title',{},g);title.textContent=n.label+' · '+n.records.length+' source records · Drag to rearrange';
    g.addEventListener('click',()=>{if(!dragged)showDetails(n,'node');});
    g.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;
      dragged=false;
      dragState={id:n.id,startX:event.clientX,startY:event.clientY,origin:p,bounds:bounds.get(n.id)};
      canvas.setPointerCapture(event.pointerId);
    });
    g.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();showDetails(n,'node');}
      const delta={ArrowLeft:[-10,0],ArrowRight:[10,0],ArrowUp:[0,-10],ArrowDown:[0,10]}[event.key];
      if(delta){event.preventDefault();manualPositions.set(positionKey(n.id),{x:p.x+delta[0],y:p.y+delta[1]});drawGraph();canvas.querySelector('[data-id="'+n.id+'"]').focus();}
    });
  });
  if(selected)canvas.querySelector('[data-id="'+selected+'"]')?.classList.add('selected');
  document.getElementById('graph-empty').hidden = nodes.length > 0;
}
function filterReport() {
  const query = search.value.toLocaleLowerCase().trim();
  const selectedDirection = direction.value;
  const project = groupSelect.value;
  let visible = 0;
  document.querySelectorAll('[data-record]').forEach(row => {
    const groups = JSON.parse(row.dataset.projects || '["."]');
    row.hidden = Boolean((selectedDirection && row.dataset.direction !== selectedDirection) || (project && !groups.includes(project)) || !row.textContent.toLocaleLowerCase().includes(query));
    if (!row.hidden) visible++;
  });
  document.getElementById('visible-count').textContent = visible + ' matching grouped records';
  ['connections', 'findings'].forEach(id => {
    const section = document.getElementById(id);
    section.querySelector('.empty').hidden = Array.from(section.querySelectorAll('[data-record]')).some(row => !row.hidden);
  });
  selected = null;
  document.getElementById('selection').textContent = 'Select a node or connection to inspect ports, paths and source evidence.';
  drawGraph();
}
canvas.addEventListener('pointermove',event=>{
  if(!dragState)return;
  const dx=event.clientX-dragState.startX,dy=event.clientY-dragState.startY;
  if(Math.abs(dx)+Math.abs(dy)<4)return;
  dragged=true;
  const matrix=canvas.getScreenCTM();
  if(!matrix)return;
  manualPositions.set(positionKey(dragState.id),{x:dragState.origin.x+dx/matrix.a,y:dragState.origin.y+dy/matrix.d});
  drawGraph();
});
canvas.addEventListener('pointerup',event=>{if(dragState){if(!dragged){const n=graph.nodes.find(n=>n.id===dragState.id);showDetails(n,'node');}dragState=null;canvas.releasePointerCapture(event.pointerId);}});
canvas.addEventListener('pointercancel',()=>{dragState=null;});
document.getElementById('reset-layout').addEventListener('click',()=>{manualPositions.clear();drawGraph();});
document.getElementById('export-svg').addEventListener('click',()=>{
  const copy=canvas.cloneNode(true);
  copy.removeAttribute('style');
  copy.setAttribute('width',canvas.viewBox.baseVal.width);
  copy.setAttribute('height',canvas.viewBox.baseVal.height);
  const style=document.createElementNS(ns,'style');style.textContent=document.querySelector('head style').textContent;copy.prepend(style);
  copy.querySelectorAll('[tabindex]').forEach(n=>n.removeAttribute('tabindex'));
  const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='netspector-network.svg';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
search.addEventListener('input', filterReport);
direction.addEventListener('change', filterReport);
groupSelect.addEventListener('change', filterReport);
document.getElementById('zoom-in').addEventListener('click',()=>{scale=Math.min(3,scale+.25);drawGraph();});
document.getElementById('zoom-out').addEventListener('click',()=>{scale=Math.max(1,scale-.25);drawGraph();});
document.getElementById('zoom-fit').addEventListener('click',()=>{scale=1;drawGraph();});
filterReport();
'''


def text(value):
    return escape(str(value if value is not None else '—'), quote=True)


def badge(status):
    tone = 'warn' if status in {'unresolved', 'candidate', 'partial'} else 'neutral' if status == 'inferred' else ''
    return f'<span class="badge {tone}">{text(status)}</span>'


def details(label, value):
    return f'<details><summary>{text(label)}</summary><pre>{text(json.dumps(value, indent=2, ensure_ascii=False))}</pre></details>' if value else ''


def render_html(report, project_name=None):
    if project_name:
        report = dict(report, project=dict(report.get('project', {}), name=project_name))
    graph = build_graph(report)
    findings = report['findings']
    roots = report.get('project', {}).get('roots', ['.'])

    def group(file):
        parent = PurePosixPath(file or '').parent
        return max((r for r in roots if r == '.' or PurePosixPath(r) == parent or PurePosixPath(r) in parent.parents), key=lambda r: len(PurePosixPath(r).parts), default='.')

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
        cards.append(f'<article class="connection" data-record="connection" data-direction="inbound" data-projects="{text(json.dumps(sorted({group(n.get("file")) for n in connection["nodes"]})))}"><div class="connection-head"><span class="namespace">Namespace · {text(connection["namespace"])}</span>{badge(connection["status"])}</div><div class="path">' + '<span class="arrow" aria-hidden="true">→</span>'.join(nodes) + f'</div>{reasons}{proof}</article>')
    rows = []
    grouped = {}
    for finding in findings:
        key = (group(finding['file']), finding['direction'], finding['target'], str(finding.get('port')))
        grouped.setdefault(key, []).append(finding)
    for (project, direction, target, _), items in sorted(grouped.items()):
        kinds = ', '.join(sorted({f['kind'] for f in items}))
        states = ''.join(badge(status) for status in sorted({f['status'] for f in items}))
        locations = sorted({f"{f['file']}:{f['line'] or '—'}" for f in items})
        location = locations[0] + (f' +{len(locations)-1}' if len(locations) > 1 else '')
        proof = details(f'{len(items)} source record(s)', items)
        rows.append(f'<tr data-record="finding" data-direction="{text(direction)}" data-projects="{text(json.dumps([project]))}"><td>{text(direction)}</td><td>{text(kinds)}</td><td class="target"><code>{text(target)}</code></td><td>{text(items[0].get("port"))}</td><td>{states}</td><td class="source"><code>{text(location)}</code>{proof}</td></tr>')
    counts = [('Projects', len(graph['projects'])), ('Unique hosts', sum(n['kind'] == 'Host' for n in graph['nodes'])), ('Connections', len(graph['edges'])), ('Source records', len(findings))]
    metrics = ''.join(f'<div class="metric"><strong>{count}</strong><span>{label}</span></div>' for label, count in counts)
    options = ''.join(f'<option value="{text(p)}">{text(graph["title"] if p == "." else p)}</option>' for p in graph['projects'])
    graph_data = text(json.dumps(graph, ensure_ascii=False, separators=(',', ':')))
    errors = ''.join(f'<div class="diagnostic"><b>{text(d["file"])}</b> · {text(d["message"])}</div>' for d in diagnostics)
    if not errors:
        errors = '<p class="section-note">No parsing diagnostics.</p>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>netspector · Network report</title><style>{STYLE}</style></head><body>
<header><div class="brand">netspector / network inventory</div><h1>{text(graph["title"])} <span>network map</span></h1><p>Projects, application servers and shared hosts. Select for evidence; drag to arrange.</p></header>
<main><div class="metrics">{metrics}</div>
<div class="toolbar"><label>Project / application<select id="project"><option value="">All projects</option>{options}</select></label><label>Search records<input id="search" type="search" placeholder="Host, service, file or namespace…"></label><label>Direction<select id="direction"><option value="">All directions</option><option value="inbound">Inbound</option><option value="outbound">Outbound</option><option value="unknown">Unknown</option></select></label><p id="visible-count" role="status" aria-live="polite"></p></div>
<noscript><style>.map-section{{display:none}}</style><p>Expand the grouped endpoints and infrastructure paths below. Enable JavaScript for the graph and local filters.</p></noscript>
<section class="map-section"><div class="map-heading"><div><h2>Network diagram</h2><p id="graph-count" class="section-note"></p></div><div class="zoom"><button id="reset-layout">Reset layout</button><button id="export-svg">Save SVG</button><button id="zoom-out" aria-label="Zoom out">−</button><button id="zoom-fit">Fit</button><button id="zoom-in" aria-label="Zoom in">+</button></div></div>
<div class="map-layout"><div class="graph-scroll"><svg id="network-svg" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Application network relationships"></svg><p class="empty" id="graph-empty" hidden>No matching nodes.</p></div><aside id="selection" aria-live="polite">Select a node or connection to inspect ports, paths and source evidence.</aside></div>
<div class="legend"><span>→ Declared direction</span><span>⇢ Candidate / unresolved</span><span>··· Configuration, direction unknown</span></div><p class="section-note">Ingress hosts are exposure addresses, not client identities. Project groups follow manifest directories; source applications are not automatically matched to Kubernetes workloads.</p></section>
<details class="inventory"><summary>Grouped endpoints · {len(rows)}</summary><section id="findings"><h2>Discovered endpoints</h2><div class="table-wrap"><table><thead><tr><th>Direction</th><th>Kind</th><th>Target</th><th>Port</th><th>Status</th><th>Source</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><p class="empty" {'hidden' if rows else ''}>No matching findings.</p></section></details>
<details class="inventory"><summary>Infrastructure paths · {len(connections)}</summary><section id="connections"><h2>Kubernetes network paths</h2><p class="section-note">Ingress → Service → selected workload → declared container port. Missing references remain visible.</p>{''.join(cards)}<p class="empty" {'hidden' if cards else ''}>No matching network paths.</p></section>
</details>
<details class="inventory" {'open' if diagnostics else ''}><summary>Scan diagnostics · {len(diagnostics)}</summary>{errors}</details>
<footer>netspector {text(__version__)} · Offline report · Search runs locally · No external assets or endpoint requests.<br>Missing namespace defaults to “default”. Static declarations and candidates, not observed traffic. Host aliases are not resolved through DNS.</footer></main><div id="graph-data" hidden>{graph_data}</div><script>{SCRIPT}</script></body></html>\n'''
