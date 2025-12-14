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
  const [refreshInterval, setRefreshInterval] = useState<number>(10000); // Default to 10 seconds
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
  const [isToggling, setIsToggling] = useState<boolean>(false);
  const plotRef = useRef<HTMLDivElement>(null);

  const toLocalISOString = (date: Date) => {
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  const handleStartTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = new Date(e.target.value);

    // Don't update state if the date is invalid
    if (isNaN(newDate.getTime()) || newDate.getTime() >= Date.now()) {
      return;
    }
    setStartTime(newDate.getTime());
  };

  const toggleLogging = async () => {
    setIsToggling(true);
    const oldIsPlotting = isPlotting; // Store current state
    const endpoint = isPlotting ? '/logging/stop' : '/logging/start/10';

    try {
      console.log(`endpoint: ${endpoint}`)
      const response = await fetch(endpoint, { method: 'POST' });
      // console.log(`body: ${response.json()}`)
      // console.log(`isPlotting: ${isPlotting}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (e: any) {
      console.error(`Failed to toggle logging: ${e.message}`);
      setIsPlotting(oldIsPlotting); // Revert on error
    } finally {
      // Always re-fetch status to ensure UI is in sync with backend
      const statusResponse = await fetch('/logging/status');
      const statusData = await statusResponse.json();
      console.log(`status: ${statusData.status}`)
      setIsPlotting(statusData.status == "running");
      setIsToggling(false);
    }
  };

  const fetchData = async (start: number, end: number): Promise<HistoryData | null> => {
    try {
      const response = await axios.get<HistoryData>(`/history/${start}/${end}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching data:', error);
      return null;
    }
  };

  useEffect(() => {
    const fetchPlottingStatus = async () => {
      try {
        const response = await fetch('/logging/status');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log(`status: ${data.status}`)
        setIsPlotting(data.status == "running");
      } catch (e: any) {
        console.error("Failed to fetch plotting status:", e);
        setIsPlotting(false);
      }
    };

    fetchPlottingStatus(); // Initial fetch
    const statusInterval = setInterval(fetchPlottingStatus, 10000); // Poll every 10 seconds

    return () => clearInterval(statusInterval);
  }, []); // Empty dependency array means this runs once on mount and cleans up on unmount

  useEffect(() => {
    const fetchAndSetData = async () => {
      const now = Date.now();
      const fetchedData = await fetchData(startTime, now);
      
      if (fetchedData && fetchedData.timestamp_ms && fetchedData.timestamp_ms.length > 0) {
        setData(fetchedData);
      }
    };

    fetchAndSetData(); // Initial fetch when startTime changes or on mount

    const intervalId = setInterval(() => {
      if (isPlotting) { // Only poll if isPlotting is true
        fetchAndSetData(); // Re-fetch all data from startTime to now
      }
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [startTime, refreshInterval, isPlotting]);

  useEffect(() => {
    if (plotRef.current) {
      const marks: Plot.Markish[] = [];
      if (data.timestamp_ms.length > 0) {
        const temperatureTypes = ['water', 'case', 'outlet', 'inlet', 'discharge', 'suction', 'evaporator', 'ambient'];
        temperatureTypes.forEach(type => {
          marks.push(
            Plot.line(data.timestamp_ms.map((t, i) => ({ x: new Date(t), y: (data as any)[type][i], type: type })), { x: 'x', y: 'y', stroke: 'type' }),
            Plot.dot([
              { x: new Date(data.timestamp_ms[0]), y: (data as any)[type][0], type: type },
              { x: new Date(data.timestamp_ms[data.timestamp_ms.length - 1]), y: (data as any)[type][data.timestamp_ms.length - 1], type: type }
            ], { x: 'x', y: 'y', stroke: 'type', symbol: 'type' })
          );
        });
      }

      const plot = Plot.plot({
        marks: marks,
        x: { type: 'time', label: 'Time', domain: [new Date(startTime), new Date()] },
        y: { label: 'Temperature (°C)' },
        
        symbol: { legend: true }, // Add a legend for symbols
        grid: true,
        width: 800, // Fixed width
        height: 400, // Fixed height
      });
      plotRef.current.replaceChildren(plot);
    }
  }, [data, startTime]);

  return (
    <div className="App">
      <h1>Reclaim Energy Data Visualizer</h1>
      <div>
        <label>
          Start Time:
          <input type="datetime-local" value={toLocalISOString(new Date(startTime))} onChange={handleStartTimeChange} />
        </label>
        <button
          onClick={toggleLogging}
          disabled={isToggling}
          style={{ backgroundColor: isPlotting ? 'green' : 'red', color: 'white' }}
        >
          {isToggling
            ? (isPlotting ? 'Turning logging OFF' : 'Turning logging ON')
            : `Logging ${isPlotting ? 'ON' : 'OFF'}`
          }
        </button>
      </div>
      <div ref={plotRef}></div>
    </div>
  );
}

export default App;
