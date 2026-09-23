from html import escape
import json
import math

import networkx as nx
import plotly.graph_objects as go
from pyvis.network import Network

from ui.theme import COLORS, LABELS


def directed_graph(nodes, edges):
    graph = nx.DiGraph()
    for r in nodes.to_dict("records"):
        graph.add_node(str(r["gid"]), **r)
    for r in edges:
        src, dst = str(r["src"]), str(r["dst"])
        if src in graph and dst in graph:
            graph.add_edge(src, dst, **r)
    return graph


def bounded_nodes(graph, selected=None, hops=1, cap=250):
    if selected is not None:
        selected = str(selected)
        if selected not in graph:
            return [], 0
        distance = nx.single_source_shortest_path_length(graph.to_undirected(as_view=True), selected, cutoff=hops)
    else:
        distance = dict.fromkeys(graph.nodes, 0)
    ids = sorted(distance, key=lambda gid: (distance[gid], -float(graph.nodes[gid].get("priority_score", 0)), gid))
    return ids[:cap], len(ids)


def ego_html(graph, selected=None, hops=1, cap=250):
    ids, total = bounded_nodes(graph, selected, hops, cap)
    subgraph = graph.subgraph(ids)
    pos = nx.spring_layout(subgraph, seed=42, iterations=40, weight="sum_kzt") if ids else {}
    net = Network(height="570px", width="100%", directed=True, cdn_resources="in_line", bgcolor="#f8fafc", font_color="#172c44")
    for gid in ids:
        r = graph.nodes[gid]
        color = COLORS.get(r.get("role"), COLORS["peripheral"])
        net.add_node(gid, label=gid, title=escape(f"{r.get('role_label', '')}\nПриоритет: {r.get('priority_score', 0):.3f}\nВходящие: {r.get('in_kzt', 0):,.0f} ₸"),
                     x=float(pos[gid][0])*600, y=float(pos[gid][1])*600,
                     size=15+18*float(r.get("priority_score", 0))+(10 if gid == str(selected) else 0),
                     color={"background": color, "border": "#111827" if r.get("is_seed") else color},
                     borderWidth=4 if r.get("is_seed") else 1,
                     shape="dot", shapeProperties={"borderDashes": r.get("visibility", "full") != "full"})
    for src, dst, r in subgraph.edges(data=True):
        amount = float(r.get("sum_kzt", 0))
        net.add_edge(src, dst, width=1+math.log1p(amount)/5,
                     title=escape(f"{src} → {dst}\n{amount:,.0f} ₸ · {r.get('n_tx', 0)} переводов"),
                     arrows="to", color="#8493a5")
    net.set_options(json.dumps({"physics": {"enabled": False}, "interaction": {"hover": True},
                                "edges": {"smooth": {"enabled": True, "type": "dynamic"}},
                                "nodes": {"font": {"size": 10}}}))
    html = net.generate_html()
    # Pyvis's stock template adds Bootstrap CDN even with inline vis.js.
    import re
    html = re.sub(r'<link\s+[^>]*href="https://cdn\.jsdelivr[^>]*>', '', html, flags=re.S)
    html = re.sub(r'<script\s+[^>]*src="https://cdn\.jsdelivr[^>]*>\s*</script>', '', html, flags=re.S)
    return html, len(ids), total


def layer_figure(nodes, edges, graph_json, selected=None, network_layout=False):
    figure = go.Figure()
    order = {"depth": True, "cluster_id": True, "priority_score": False, "gid": True}
    columns = [c for c in order if c in nodes]
    nodes = nodes.sort_values(columns, ascending=[order[c] for c in columns]).copy()
    saved = {str(r["id"]): r for r in graph_json.get("nodes", [])}
    coordinates = {}
    for depth, group in nodes.groupby("depth"):
        for i, r in enumerate(group.to_dict("records")):
            gid = str(r["gid"])
            p = saved.get(gid, {})
            if network_layout and "x" in p and "y" in p:
                coordinates[gid] = (p["x"], p["y"])
            else:
                coordinates[gid] = (float(depth)+(i % 7-3)*.022, (i+.5)/len(group))
    visible_edges = [r for r in edges if str(r["src"]) in coordinates and str(r["dst"]) in coordinates]
    chosen = sorted(visible_edges, key=lambda r: (-r["sum_kzt"], str(r["src"]), str(r["dst"])))[:400]
    max_amount = max((r["sum_kzt"] for r in chosen), default=1)
    neighbors = {str(selected)} if selected is not None else set()
    for r in visible_edges:
        if str(selected) in (str(r["src"]), str(r["dst"])):
            neighbors.update([str(r["src"]), str(r["dst"])])
    # Four opacity groups keep figure size small while encoding transfer volume.
    for bucket in range(4):
        xs, ys = [], []
        for r in chosen:
            b = min(3, int(4*math.log1p(r["sum_kzt"])/math.log1p(max_amount))) if max_amount > 0 else 0
            if b == bucket:
                x1,y1 = coordinates[str(r["src"])]; x2,y2 = coordinates[str(r["dst"])]
                xs += [x1,x2,None]; ys += [y1,y2,None]
        figure.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=.7, color=f"rgba(92,112,139,{.08+.08*bucket})"), hoverinfo="skip", showlegend=False))
    for r in chosen[:100]:
        x1,y1 = coordinates[str(r["src"])]; x2,y2 = coordinates[str(r["dst"])]
        figure.add_annotation(x=x2, y=y2, ax=x1, ay=y1, xref="x", yref="y", axref="x", ayref="y",
                              showarrow=True, arrowhead=2, arrowsize=.6, arrowwidth=.5, arrowcolor="#99a8ba", opacity=.4)
    for role, group in nodes.groupby("role"):
        records = group.to_dict("records")
        ids = [str(r["gid"]) for r in records]
        figure.add_trace(go.Scatter(
            x=[coordinates[g][0] for g in ids], y=[coordinates[g][1] for g in ids], mode="markers", name=LABELS[role],
            customdata=[[g, r["role_label"], float(r["priority_score"]), escape(str(r["evidence"]))] for g,r in zip(ids,records)],
            hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>Приоритет %{customdata[2]:.3f}<br>%{customdata[3]}<extra></extra>",
            marker=dict(color=COLORS[role], size=[max(4, min(22, 4+math.log1p(float(r.get("tracked_in", 0)))) ) for r in records],
                        opacity=[1 if not neighbors or g in neighbors else .2 for g in ids],
                        line=dict(color=["#111827" if r.get("is_seed") else "#64748b" for r in records],
                                  width=[3 if r.get("rank", 9999) <= 30 or r.get("is_seed") else .5 for r in records]))))
    if not network_layout:
        figure.add_vrect(x0=3.7, x1=4.3, fillcolor="#e2e8f0", opacity=.4, line_width=0, layer="below")
        figure.add_annotation(x=4, y=1.09, text="Обрыв обхода:<br>исходящие не собраны", showarrow=False, font=dict(size=11, color="#64748b"))
        figure.update_xaxes(tickvals=list(range(5)), ticktext=["Seed · 0", "Колено 1", "Колено 2", "Колено 3", "Колено 4"], range=[-.4,4.4])
    figure.update_yaxes(visible=False)
    figure.update_layout(height=650, paper_bgcolor="white", plot_bgcolor="#fafcfe", margin=dict(l=10,r=10,t=50,b=30),
                         legend=dict(orientation="h", y=-.12), clickmode="event+select")
    return figure, len(visible_edges)
