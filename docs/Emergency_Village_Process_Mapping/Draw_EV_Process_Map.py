import networkx as nx
import matplotlib.pyplot as plt

# Create a graph
G = nx.DiGraph()

# Add nodes
G.add_nodes_from(['999',
                  '111',
                  'GP',
                  'Self-referral',
                  'Walk-in',
                  'Direct Ref',
                  'Ambulance',
                  'Reception',
                  'A Majors',
                  'P Majors',
                  'Resus',
                  'Isolation',
                  'MH Room',
                  'Urgent WR',
                  'ASU/SAU',
                  'AFU/FAU',
                  'AAU/AMU',
                  'ED A IA',
                  'ED P IA',
                  'Streaming',
                  'Triaging',
                  'Surge',
                  'PAU',
                  'ICU',
                  'M Ward',
                  'S Ward',
                  'OHD',
                  'Theatres',
                  'Diagnostics',
                  'D Lounge',
                  'UTC/Minors',
                  'SDEC',
                  'CDU',
                  'MH Dep',
                  'Exit'
                  ])

# Define node colors
node_colors = {
                  '999': 'gray',
                  '111': 'gray',
                  'GP': 'gray',
                  'Self-referral': 'gray',
                  'Walk-in': 'orange',
                  'Direct Ref': 'orange',
                  'Ambulance': 'orange',
                  'Reception': 'red',
                  'Streaming': 'red',
                  'Triaging': 'red',
                  'ED A IA': 'lavender',
                  'ED P IA': 'lavender',
                  'Resus': 'lavender',
                  'P Majors': 'lavender',
                  'A Majors': 'lavender',
                  'Isolation': 'lavender',
                  'MH Room': 'lavender',
                  'PAU': 'lavender',
                  'Urgent WR': 'green',
                  'ASU/SAU': 'green',
                  'AFU/FAU': 'green',
                  'AAU/AMU': 'green',
                  'UTC/Minors': 'green',
                  'SDEC': 'green',
                  'CDU': 'green',
                  'Diagnostics': 'skyblue',
                  'Surge': 'skyblue',
                  'ICU': 'pink',
                  'MH Dep': 'pink',
                  'M Ward': 'pink',
                  'S Ward': 'pink',
                  'OHD': 'pink',
                  'Theatres': 'pink',
                  'D Lounge': 'pink',
                  'Exit': 'brown'
}
# Add edges with attributes
edges_with_acuity = [('999', 'Ambulance', '1-2'),
                     ('999', 'Ambulance', '3'),
                     ('999', 'Ambulance', '4-5'),
                     ('999', 'Walk-in', '1-2'),
                     ('999', 'Walk-in', '3'),
                     ('999', 'Walk-in', '4-5'),
                     ('111', 'Ambulance', '1-2'),
                     ('111', 'Ambulance', '3'),
                     ('111', 'Walk-in', '4-5'),
                     ('111', 'Direct Ref', '4-5'),
                     ('GP', 'Ambulance', '1-2'),
                     ('GP', 'Ambulance', '3'),
                     ('GP', 'Walk-in', '4-5'),
                     ('GP', 'Direct Ref', '3'),
                     ('111', 'Direct Ref', '3'),
                     ('GP', 'Direct Ref', '4-5'),
                     ('111', 'Direct Ref', '4-5'),
                     ('Self-referral', 'Walk-in', '1-2'),
                     ('Self-referral', 'Walk-in', '3'),
                     ('Self-referral', 'Walk-in', '4-5'),
                     ('Ambulance', 'MH Room', '1-2'),
                     ('Ambulance', 'Resus', '1-2'),
                     ('Ambulance', 'Isolation', '1-2'),
                     ('Ambulance', 'Triaging', '3'),
                     ('Ambulance', 'MH Room', '3'),
                     ('Ambulance', 'A Majors', '3'),
                     ('Ambulance', 'P Majors', '3'),
                     ('Ambulance', 'UTC/Minors', '3'),
                     ('Ambulance', 'SDEC', '3'),
                     ('Ambulance', 'Triaging', '4-5'),
                     ('Ambulance', 'MH Room', '4-5'),
                     ('Ambulance', 'UTC/Minors', '4-5'),
                     ('Ambulance', 'SDEC', '4-5'),
                     ('Walk-in', 'Reception', '1-2'),
                     ('Walk-in', 'Reception', '3'),
                     ('Walk-in', 'Urgent WR', '3'),
                     ('Walk-in', 'Reception', '4-5'),
                     ('Walk-in', 'Urgent WR', '4-5'),
                     ('Direct Ref', 'ED A IA', '3'),
                     ('Direct Ref', 'ED P IA', '3'),
                     ('Direct Ref', 'Urgent WR', '3'),
                     ('Direct Ref', 'ED P IA', '4-5'),
                     ('Direct Ref', 'Urgent WR', '4-5'),
                     ('Reception', 'Streaming', '1-2'),
                     ('Reception', 'Isolation', '1-2'),
                     ('Reception', 'Streaming', '3'),
                     ('Reception', 'Streaming', '4-5'),
                     ('Streaming', 'Triaging', '1-2'),
                     ('Streaming', 'Triaging', '3'),
                     ('Streaming', 'Triaging', '4-5'),
                     ('Triaging', 'ED A IA', '1-2'),
                     ('Triaging', 'ED P IA', '1-2'),
                     ('Triaging', 'ED A IA', '3'),
                     ('Triaging', 'ED P IA', '3'),
                     ('Triaging', 'Urgent WR', '3'),
                     ('Triaging', 'ED P IA', '4-5'),
                     ('Triaging', 'Urgent WR', '4-5'),
                     ('ED P IA', 'Resus', '1-2'),
                     ('ED P IA', 'Surge', '1-2'),
                     ('ED P IA', 'P Majors', '3'),
                     ('ED P IA', 'Surge', '3'),
                     ('ED P IA', 'PAU', '4-5'),
                     ('ED P IA', 'Surge', '4-5'),
                     ('ED A IA', 'Resus', '1-2'),
                     ('ED A IA', 'MH Room', '1-2'),
                     ('ED A IA', 'Surge', '1-2'),
                     ('ED A IA', 'A Majors', '3'),
                     ('ED A IA', 'MH Room', '3'),
                     ('ED A IA', 'Surge', '3'),
                    ('Resus', 'ICU', '1-2'),
                    ('Resus', 'Theatres', '1-2'),
                    ('Resus', 'Diagnostics', '1-2'),
                    #('Resus', 'D - MRI', '1-2'),
                    ('P Majors', 'Theatres', '3'),
                    ('P Majors', 'M Ward', '3'),
                    ('P Majors', 'S Ward', '3'),
                    ('P Majors', 'OHD', '3'),
                    ('P Majors', 'Diagnostics', '3'),
                    #('P Majors', 'D - MRI', '3'),
                    ('P Majors', 'MH Dep', '3'),
                    ('A Majors', 'Theatres', '3'),
                    ('A Majors', 'M Ward', '3'),
                    ('A Majors', 'S Ward', '3'),
                    ('A Majors', 'OHD', '3'),
                    ('A Majors', 'Diagnostics', '3'),
                    #('A Majors', 'D - MRI', '3'),
                    ('A Majors', 'MH Dep', '3'),
                    ('Isolation', 'ICU', '1-2'),
                    ('Isolation', 'M Ward', '1-2'),
                    ('Isolation', 'D Lounge', '1-2'),
                    ('MH Room', 'MH Dep', '1-2'),
                    ('MH Room', 'D Lounge', '1-2'),
                    ('MH Room', 'MH Dep', '3'),
                    ('MH Room', 'D Lounge', '3'),
                    ('MH Room', 'MH Dep', '4-5'),
                    ('MH Room', 'D Lounge', '4-5'),
                    ('PAU', 'Diagnostics', '4-5'),
                    #('PAU', 'D - X-Ray', '4-5'),
                    #('PAU', 'D - MRI', '4-5'),
                    #('PAU', 'D - Bloods', '4-5'),
                    ('PAU', 'D Lounge', '4-5'),
                    ('Urgent WR', 'AAU/AMU', '3'),
                    ('Urgent WR', 'AFU/FAU', '3'),
                    ('Urgent WR', 'ASU/SAU', '3'),
                    ('Urgent WR', 'UTC/Minors', '3'),
                    ('Urgent WR', 'SDEC', '3'),
                    ('Urgent WR', 'CDU', '3'),
                    ('Urgent WR', 'Surge', '3'),
                    ('Urgent WR', 'AAU/AMU', '4-5'),
                    ('Urgent WR', 'AFU/FAU', '4-5'),
                    ('Urgent WR', 'ASU/SAU', '4-5'),
                    ('Urgent WR', 'UTC/Minors', '4-5'),
                    ('Urgent WR', 'SDEC', '4-5'),
                    ('Urgent WR', 'CDU', '4-5'),
                    ('Urgent WR', 'Surge', '4-5'),
                    ('AAU/AMU', 'Diagnostics', '3'),
                    #('AAU/AMU', 'D - X-Ray', '3'),
                    #('AAU/AMU', 'D - MRI', '3'),
                    #('AAU/AMU', 'D - Bloods', '3'),
                    ('AAU/AMU', 'OHD', '3'),
                    ('AAU/AMU', 'D Lounge', '3'),
                    ('AAU/AMU', 'Diagnostics', '4-5'),
                    #('AAU/AMU', 'D - X-Ray', '4-5'),
                    #('AAU/AMU', 'D - MRI', '4-5'),
                    #('AAU/AMU', 'D - Bloods', '4-5'),
                    ('AAU/AMU', 'OHD', '4-5'),
                    ('AAU/AMU', 'D Lounge', '4-5'),
                    ('AFU/FAU', 'Diagnostics', '3'),
                    #('AFU/FAU', 'D - X-Ray', '3'),
                    #('AFU/FAU', 'D - MRI', '3'),
                    #('AFU/FAU', 'D - Bloods', '3'),
                    ('AFU/FAU', 'OHD', '3'),
                    ('AFU/FAU', 'D Lounge', '3'),
                    ('AFU/FAU', 'Diagnostics', '4-5'),
                    #('AFU/FAU', 'D - X-Ray', '4-5'),
                    #('AFU/FAU', 'D - MRI', '4-5'),
                    #('AFU/FAU', 'D - Bloods', '4-5'),
                    ('AFU/FAU', 'OHD', '4-5'),
                    ('AFU/FAU', 'D Lounge', '4-5'),
                    ('ASU/SAU', 'Diagnostics', '3'),
                    #('ASU/SAU', 'D - X-Ray', '3'),
                    #('ASU/SAU', 'D - MRI', '3'),
                    #('ASU/SAU', 'D - Bloods', '3'),
                    ('ASU/SAU', 'OHD', '3'),
                    ('ASU/SAU', 'S Ward', '3'),
                    ('ASU/SAU', 'D Lounge', '3'),
                    ('ASU/SAU', 'Diagnostics', '4-5'),
                    #('ASU/SAU', 'D - X-Ray', '4-5'),
                    #('ASU/SAU', 'D - MRI', '4-5'),
                    #('ASU/SAU', 'D - Bloods', '4-5'),
                    ('ASU/SAU', 'OHD', '4-5'),
                    ('ASU/SAU', 'S Ward', '4-5'),
                    ('ASU/SAU', 'D Lounge', '4-5'),
                    ('UTC/Minors', 'Diagnostics', '3'),
                    #('UTC/Minors', 'D - X-Ray', '3'),
                    #('UTC/Minors', 'D - MRI', '3'),
                    #('UTC/Minors', 'D - Bloods', '3'),
                    ('UTC/Minors', 'D Lounge', '3'),
                    ('UTC/Minors', 'Diagnostics', '4-5'),
                    #('UTC/Minors', 'D - X-Ray', '4-5'),
                    #('UTC/Minors', 'D - MRI', '4-5'),
                    #('UTC/Minors', 'D - Bloods', '4-5'),
                    ('UTC/Minors', 'D Lounge', '4-5'),
                    ('SDEC', 'Diagnostics', '3'),
                    #('SDEC', 'D - MRI', '3'),
                    ('SDEC', 'M Ward', '3'),
                    ('SDEC', 'S Ward', '3'),
                    ('SDEC', 'Theatres', '3'),
                    ('SDEC', 'OHD', '3'),
                    ('SDEC', 'D Lounge', '3'),
                    ('SDEC', 'Diagnostics', '4-5'),
                    #('SDEC', 'D - X-Ray', '4-5'),
                    #('SDEC', 'D - MRI', '4-5'),
                    #('SDEC', 'D - Bloods', '4-5'),
                    ('SDEC', 'D Lounge', '4-5'),
                    ('CDU', 'Diagnostics', '3'),
                    #('CDU', 'D - MRI', '3'),
                    ('CDU', 'M Ward', '3'),
                    ('CDU', 'S Ward', '3'),
                    ('CDU', 'OHD', '3'),
                    ('CDU', 'D Lounge', '3'),
                    ('CDU', 'Diagnostics', '4-5'),
                    #('CDU', 'D - X-Ray', '4-5'),
                    #('CDU', 'D - MRI', '4-5'),
                    #('CDU', 'D - Bloods', '4-5'),
                    ('CDU', 'D Lounge', '4-5'),
                    ('Diagnostics', 'Resus', '1-2'),
                    ('Diagnostics', 'Surge', '1-2'),
                    #('Diagnostics', 'D - MRI', '1-2'),
                    ('Diagnostics', 'A Majors', '3'),
                    ('Diagnostics', 'P Majors', '3'),
                    ('Diagnostics', 'Surge', '3'),
                    ('Diagnostics', 'AAU/AMU', '3'),
                    ('Diagnostics', 'AFU/FAU', '3'),
                    ('Diagnostics', 'ASU/SAU', '3'),
                    ('Diagnostics', 'UTC/Minors', '3'),
                    ('Diagnostics', 'SDEC', '3'),
                    ('Diagnostics', 'CDU', '3'),
                    #('D - CT', 'D - MRI', '3'),
                    ('Diagnostics', 'PAU', '4-5'),
                    ('Diagnostics', 'Surge', '4-5'),
                    ('Diagnostics', 'AAU/AMU', '4-5'),
                    ('Diagnostics', 'AFU/FAU', '4-5'),
                    ('Diagnostics', 'ASU/SAU', '4-5'),
                    ('Diagnostics', 'UTC/Minors', '4-5'),
                    ('Diagnostics', 'SDEC', '4-5'),
                    ('Diagnostics', 'CDU', '4-5'),
                    #('D - CT', 'D - X-Ray', '4-5'),
                    #('D - CT', 'D - MRI', '4-5'),
                    #('D - CT', 'D - Bloods', '4-5'),
                    #('D - Bloods', 'D - X-Ray', '1-2'),
                    #('D - Bloods', 'AAU/AMU', '3'),
                    #('D - Bloods', 'AFU/FAU', '3'),
                    #('D - Bloods', 'ASU/SAU', '3'),
                    #('D - Bloods', 'UTC/Minors', '3'),
                    #('D - Bloods', 'SDEC', '3'),
                    #('D - Bloods', 'CDU', '3'),
                    #('D - Bloods', 'D - X-Ray', '3'),
                    #('D - Bloods', 'Surge', '4-5'),
                    #('D - Bloods', 'PAU', '4-5'),
                    #('D - Bloods', 'AAU/AMU', '4-5'),
                    #('D - Bloods', 'AFU/FAU', '4-5'),
                    #('D - Bloods', 'ASU/SAU', '4-5'),
                    #('D - Bloods', 'UTC/Minors', '4-5'),
                    #('D - Bloods', 'SDEC', '4-5'),
                    #('D - Bloods', 'CDU', '4-5'),
                    #('D - Bloods', 'D - X-Ray', '4-5'),
                    #('D - Bloods', 'D - MRI', '4-5'),
                    #('D - Bloods', 'D - CT', '4-5'),
                    #('D - X-Ray', 'D - Bloods', '1-2'),
                    #('D - X-Ray', 'AAU/AMU', '3'),
                    #('D - X-Ray', 'AFU/FAU', '3'),
                    #('D - X-Ray', 'ASU/SAU', '3'),
                    #('D - X-Ray', 'UTC/Minors', '3'),
                    #('D - X-Ray', 'SDEC', '3'),
                    #('D - X-Ray', 'CDU', '3'),
                    #('D - X-Ray', 'D - Bloods', '3'),
                    #('D - X-Ray', 'PAU', '4-5'),
                    #('D - X-Ray', 'Surge', '4-5'),
                    #('D - X-Ray', 'AAU/AMU', '4-5'),
                    #('D - X-Ray', 'AFU/FAU', '4-5'),
                    #('D - X-Ray', 'ASU/SAU', '4-5'),
                    #('D - X-Ray', 'UTC/Minors', '4-5'),
                    #('D - X-Ray', 'SDEC', '4-5'),
                    #('D - X-Ray', 'CDU', '4-5'),
                    #('D - X-Ray', 'D - Bloods', '4-5'),
                    #('D - X-Ray', 'D - MRI', '4-5'),
                    #('D - X-Ray', 'D - CT', '4-5'),
                    #('D - MRI', 'Resus', '1-2'),
                    #('D - MRI', 'Surge', '1-2'),
                    #('D - MRI', 'D - CT', '1-2'),
                    #('D - MRI', 'A Majors', '3'),
                    #('D - MRI', 'P Majors', '3'),
                    #('D - MRI', 'Surge', '3'),
                    #('D - MRI', 'AAU/AMU', '3'),
                    #('D - MRI', 'AFU/FAU', '3'),
                    #('D - MRI', 'ASU/SAU', '3'),
                    #('D - MRI', 'UTC/Minors', '3'),
                    #('D - MRI', 'SDEC', '3'),
                    #('D - MRI', 'CDU', '3'),
                    #('D - MRI', 'D - CT', '3'),
                    #('D - MRI', 'PAU', '4-5'),
                    #('D - MRI', 'Surge', '4-5'),
                    #('D - MRI', 'AAU/AMU', '4-5'),
                    #('D - MRI', 'AFU/FAU', '4-5'),
                    #('D - MRI', 'ASU/SAU', '4-5'),
                    #('D - MRI', 'UTC/Minors', '4-5'),
                    #('D - MRI', 'SDEC', '4-5'),
                    #('D - MRI', 'CDU', '4-5'),
                    #('D - MRI', 'D - Bloods', '4-5'),
                    #('D - MRI', 'D - X-Ray', '4-5'),
                    #('D - MRI', 'D - CT', '4-5'),
                    ('Surge', 'Diagnostics', '1-2'),
                    #('Surge', 'D - MRI', '1-2'),
                    ('Surge', 'Theatres', '1-2'),
                    ('Surge', 'M Ward', '1-2'),
                    ('Surge', 'S Ward', '1-2'),
                    ('Surge', 'OHD', '1-2'),
                    ('Surge', 'D Lounge', '1-2'),
                    ('Surge', 'Diagnostics', '3'),
                    #('Surge', 'D - MRI', '3'),
                    ('Surge', 'Theatres', '3'),
                    ('Surge', 'M Ward', '3'),
                    ('Surge', 'S Ward', '3'),
                    ('Surge', 'OHD', '3'),
                    ('Surge', 'D Lounge', '3'),
                    ('Surge', 'Diagnostics', '4-5'),
                    #('Surge', 'D - MRI', '4-5'),
                    #('Surge', 'D - Bloods', '4-5'),
                    #('Surge', 'D - X-Ray', '4-5'),
                    ('Surge', 'M Ward', '4-5'),
                    ('Surge', 'S Ward', '4-5'),
                    ('Surge', 'OHD', '4-5'),
                    ('Surge', 'D Lounge', '4-5'),
                    ('ICU', 'M Ward', '1-2'),
                    ('ICU', 'S Ward', '1-2'),
                    ('ICU', 'OHD', '1-2'),
                    ('ICU', 'Theatres', '1-2'),
                    ('MH Dep', 'D Lounge', '1-2'),
                    ('MH Dep', 'D Lounge', '3'),
                    ('MH Dep', 'D Lounge', '4-5'),
                    ('Theatres', 'S Ward', '1-2'),
                    ('Theatres', 'S Ward', '3'),
                    ('S Ward', 'OHD', '1-2'),
                    ('S Ward', 'D Lounge', '1-2'),
                    ('S Ward', 'OHD', '3'),
                    ('S Ward', 'D Lounge', '3'),
                    ('S Ward', 'OHD', '4-5'),
                    ('S Ward', 'D Lounge', '4-5'),
                    ('M Ward', 'OHD', '1-2'),
                    ('M Ward', 'D Lounge', '1-2'),
                    ('M Ward', 'OHD', '3'),
                    ('M Ward', 'D Lounge', '3'),
                    ('M Ward', 'OHD', '4-5'),
                    ('M Ward', 'D Lounge', '4-5'),
                    ('OHD', 'D Lounge', '1-2'),
                    ('OHD', 'D Lounge', '3'),
                    ('OHD', 'D Lounge', '4-5'),
                    ('D Lounge', 'Exit', '1-2'),
                    ('D Lounge', 'Exit', '3'),
                    ('D Lounge', 'Exit', '4-5')

                     ]

# Filter edges based on acuity
edges_with_acuity_filtered = [(source, target, acuity) for source, target, acuity in edges_with_acuity if acuity == '4-5']
#edges_with_acuity_filtered = [(source, target, acuity) for source, target, acuity in edges_with_acuity]

# Merge edges with the same source and target nodes
merged_edges = {}
for source, target, acuity in edges_with_acuity_filtered:
    if (source, target) in merged_edges:
        merged_edges[(source, target)].append(acuity)
    else:
        merged_edges[(source, target)] = [acuity]

# Add merged edges to the graph with acuity information preserved
for (source, target), acuities in merged_edges.items():
    G.add_edge(source, target, acuities=acuities)

# Draw the graph
pos = nx.kamada_kawai_layout(G)  # positions for all nodes

# Draw the graph
fig, ax = plt.subplots()

# Remove isolated nodes
isolated_nodes = [node for node in G.nodes() if G.degree(node) == 0]
G.remove_nodes_from(isolated_nodes)

default_color = 'gray'
node_color = [node_colors.get(node, default_color) for node in G.nodes()]

nx.draw(G, pos, with_labels=True, node_color=node_color, node_size=4000, font_size=9, font_weight='bold', arrows=True)

# Label edges with different colors based on acuity
edge_labels = {(u, v): ", ".join(attr['acuities']) for u, v, attr in G.edges(data=True)}
edge_colors = []
for edge in G.edges():
    u, v = edge
    acuities = edge_labels.get((u, v), '').split(', ')
    # Choose a color based on the highest acuity level among merged edges
    max_acuity = max(acuities)
    if max_acuity == '1-2':
        edge_colors.append('black')
    elif max_acuity == '3':
        edge_colors.append('black')
    elif max_acuity == '4-5':
        edge_colors.append('black')

nx.draw_networkx_edge_labels(G, pos, edge_labels={}, font_color='black') #edge_labels=edge_labels
nx.draw_networkx_edges(G, pos, edge_color=edge_colors)

# Variables to track dragging state
dragging = False
dragged_node = None

# Function to handle node dragging
def on_press(event):
    global dragging, dragged_node
    if event.inaxes == ax:
        x, y = event.xdata, event.ydata
        closest_node = min(pos.keys(), key=lambda node: ((pos[node][0] - x) ** 2 + (pos[node][1] - y) ** 2))
        if ((pos[closest_node][0] - x) ** 2 + (pos[closest_node][1] - y) ** 2) < 0.01:  # Threshold for node drag
            dragging = True
            dragged_node = closest_node

def on_release(event):
    global dragging, dragged_node
    if dragging:
        x, y = event.xdata, event.ydata
        pos[dragged_node] = x, y
        ax.clear()  # Clear the previous plot
        nx.draw(G, pos, with_labels=True, node_color=node_color, node_size=4000, font_size=9, font_weight='bold', arrows=True, ax=ax)
        nx.draw_networkx_edge_labels(G, pos, edge_labels={}, font_color='black') #edge_labels=edge_labels
        nx.draw_networkx_edges(G, pos, edge_color=edge_colors)
        fig.canvas.draw_idle()  # Update the canvas
    dragging = False
    dragged_node = None

# Connect event handlers
fig.canvas.mpl_connect('button_press_event', on_press)
fig.canvas.mpl_connect('button_release_event', on_release)

plt.title('Acuity 1-2 Pathway')
plt.show()