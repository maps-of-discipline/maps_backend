from itertools import cycle

type_colors = cycle(['#90b3e7', '#c895f8', '#7cbbb4', '#75cada', '#db8480'])


for i, color in zip(range(1, 100), type_colors):
    print(i, color)