import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import * as Plot from '@observablehq/plot';

interface HistoryData {
  timestamp_ms: number[];
  pump: boolean[];
  case: number[];
  water: number[];
  outlet: number[];
  inlet: number[];
  discharge: number[];
  suction: number[];
  evaporator: number[];
  ambient: number[];
  compspeed: number[];
  waterspeed: number[];
  fanspeed: number[];
  power: number[];
  current: number[];
  hours: number[];
  starts: number[];
  boost: boolean[];
}

function App() {
  const [startTime, setStartTime] = useState<number>(Date.now() - 3600000); // Default to 1 hour ago
  const [refreshInterval, setRefreshInterval] = useState<number>(5000); // Default to 5 seconds
  const [data, setData] = useState<HistoryData>({
    timestamp_ms: [],
    pump: [],
    case: [],
    water: [],
    outlet: [],
    inlet: [],
    discharge: [],
    suction: [],
    evaporator: [],
    ambient: [],
    compspeed: [],
    waterspeed: [],
    fanspeed: [],
    power: [],
    current: [],
    hours: [],
    starts: [],
    boost: [],
  });
  const [isPlotting, setIsPlotting] = useState<boolean>(false);
  const plotRef = useRef<HTMLDivElement>(null);
  const lastFetchTime = useRef<number | null>(null);

  const fetchData = async (start: number, end: number): Promise<HistoryData | null> => {
    try {
      const response = await axios.get<HistoryData>(`/history/${start}/${end}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching data:', error);
      return null;
    }
  };

  const startPlotting = async () => {
    setIsPlotting(true);
    const now = Date.now();
    const initialData = await fetchData(startTime, now);
    if (initialData) {
      setData(initialData);
      lastFetchTime.current = now;
    }
  };

  useEffect(() => {
    let intervalId: NodeJS.Timeout;
    if (isPlotting) {
      intervalId = setInterval(async () => {
        const now = Date.now();
        if (lastFetchTime.current) {
          const newData = await fetchData(lastFetchTime.current, now);
          if (newData) {
            setData(prevData => {
              const updatedData: HistoryData = { ...prevData };
              for (const key in newData) {
                if (Object.prototype.hasOwnProperty.call(newData, key)) {
                  updatedData[key as keyof HistoryData] = [...prevData[key as keyof HistoryData], ...newData[key as keyof HistoryData]] as any;
                }
              }
              return updatedData;
            });
            lastFetchTime.current = now;
          }
        }
      }, refreshInterval);
    }
    return () => clearInterval(intervalId);
  }, [isPlotting, refreshInterval]);

  useEffect(() => {
    if (isPlotting && data.timestamp_ms.length > 0 && plotRef.current) {
      const plot = Plot.plot({
        marks: [
          Plot.line(data.timestamp_ms.map((t, i) => ({ x: new Date(t), y: data.water[i] })), { x: 'x', y: 'y' }),
          Plot.dot(data.timestamp_ms.map((t, i) => ({ x: new Date(t), y: data.water[i] })), { x: 'x', y: 'y' })
        ],
        x: { type: 'time', label: 'Time' },
        y: { label: 'Temperature' },
        grid: true,
      });
      plotRef.current.replaceChildren(plot);
    }
  }, [data, isPlotting]);

  return (
    <div className="App">
      <h1>Reclaim Energy Data Visualizer</h1>
      <div>
        <label>
          Start Time (Unix Epoch ms):
          <input type="number" value={startTime} onChange={e => setStartTime(parseInt(e.target.value, 10))} />
        </label>
        <label>
          Update Interval (ms):
          <input type="number" value={refreshInterval} onChange={e => setRefreshInterval(parseInt(e.target.value, 10))} />
        </label>
        <button onClick={startPlotting} disabled={isPlotting}>
          {isPlotting ? 'Plotting...' : 'Start Plotting'}
        </button>
      </div>
      <div ref={plotRef}></div>
    </div>
  );
}

export default App;
