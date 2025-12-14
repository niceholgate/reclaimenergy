import matplotlib.pyplot as plt
import pandas as pd

data = pd.read_csv('output.csv')
cols = data.columns


# data = data[(data['timestamp_ms'] > 1753290000000) & (data['timestamp_ms'] < 1753453200000)]
data.sort_values(by='timestamp_ms', ascending=True, inplace=True)
plt.plot(data['timestamp_ms'], data['outlet'])
plt.plot(data['timestamp_ms'], data['discharge'])
plt.legend(['outlet', 'discharge'])
plt.ylim([0, 100])
plt.yticks(list(range(0, 105, 5)))
plt.plot(data['timestamp_ms'], [int(b=='t') for b in list(data['boost'])])
plt.plot(data['timestamp_ms'], [int(b=='t')*2 for b in list(data['boost'])])

plt.show()




