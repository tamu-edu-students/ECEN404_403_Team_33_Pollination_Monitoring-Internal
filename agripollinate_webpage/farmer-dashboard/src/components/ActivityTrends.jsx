import activityStore from "../state/activityStore.jsx";
import insectStore from "../state/insectStore.jsx";  
import React, { useEffect, useState } from "react";
import Card from "./Card";

export default function ActivityTrends() {
  // Local state to hold the activity array. This pulls initial state from the global activityStore.
  const [activity, setActivity] = useState(activityStore.getState().activity);
  const [storeState, setStoreState] = useState(insectStore.getState());
  
  // Subscribe to activityStore updates on mount; update local state when store changes.
  useEffect(() => activityStore.subscribe(s => setActivity(s.activity)), []);
  useEffect(() => insectStore.subscribe(s => setStoreState(s)), []);

  // Function to consistently assign a color to each species in the legend/bars
  const colorMap = {};
  [...(storeState.pollinators || []), ...(storeState.pests || [])].forEach(item => {
    colorMap[item.label] = item.color;
  });

  const colorForSpecies = s => colorMap[s] || '#888';  // fallback color if not found

  // === Aggregate activity entries into {hour: {species: count}} for fast graph lookup ===
  // Example: {14: {Bee: 2, Aphid: 1}, ...}
  const hourSpeciesCount = {};
  activity.forEach(({ hour, species }) => {
    if (!hourSpeciesCount[hour]) hourSpeciesCount[hour] = {};
    hourSpeciesCount[hour][species] = (hourSpeciesCount[hour][species] || 0) + 1;
  });

  // Get a list of all unique observed species (for legend/bar colors)
  const speciesSet = new Set();
  Object.values(hourSpeciesCount).forEach(obj =>
    Object.keys(obj).forEach(s => speciesSet.add(s))
  );
  const speciesList = Array.from(speciesSet);

  // Array [0 .. 23] for each hour (x-axis bins of chart)
  const hours = Array.from({length:24}, (_,i) => i);

  // Find the maximum bar height for y-axis scaling (sum all stacks in busiest hour)
  const maxCount = Math.max(1, ...Object.values(hourSpeciesCount)
    .map(obj => Object.values(obj).reduce((sum, val) => sum + val, 0)));

  // Create Y-axis ticks (at most 6, evenly spaced from max down to zero)
  const yTicks = Array.from({length: Math.min(6, maxCount+1)}, (_,i) =>
    Math.round((maxCount * (Math.min(6,maxCount+1)-1-i)) /
               (Math.min(6,maxCount+1)-1))
  );

  return (
    <Card className="col-span-3 bg-white border-2 border-blue-200 rounded-lg shadow-lg p-6">
      {/* Chart header */}
      <div className="flex items-center justify-between mb-3">
        <div className="font-semibold text-slate-700">Hourly Activity Trends</div>
        <div className="text-sm text-slate-400">Updated just now</div>
      </div>
      <div className="flex w-full mt-2 overflow-x-auto">
        {/* Y-axis 'count' label, shown rotated vertically */}
        <div className="flex items-center mr-2">
          <div className="text-xs text-slate-600 rotate-[-90deg] origin-center">
            count
          </div>
        </div>
        {/* Y-axis tick labels (numbers, positioned spaced out vertically) */}
        <div className="flex flex-col justify-between h-[100px] pr-2"
             style={{height: 110, minWidth: 24}}>
          {yTicks.map(val => (
            <div
              key={val}
              style={{
                height: `${110/(yTicks.length-1)}px`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end'
              }}
              className="text-xs text-slate-500 pr-1"
            >
              {val}
            </div>
          ))}
        </div>
        {/* Chart+X label wrapper */}
        <div className="flex flex-col items-center" style={{ minWidth: 500 }}>
          {/* Stacked bar chart area */}
          <div style={{ height: 110 }} className="flex items-end relative w-full">
            {hours.map(hour => {
              // Get map of species -> count for each hour
              const hrObj = hourSpeciesCount[hour] || {};
              return (
                <div key={hour} className="flex flex-col items-center mx-0.5" style={{ width: 32 }}>
                  {/* For each observed species, stack a color bar if count > 0 */}
                  {speciesList.map(s => {
                    const val = hrObj[s] || 0;
                    if (!val) return null;
                    // Scale bar height 0..100% of area based on maxCount (at least 4px to see)
                    const h = Math.max(4, (val / maxCount) * 100);
                    return (
                      <div
                        key={s}
                        style={{
                          height: h,
                          width: 14,
                          background: colorForSpecies(s),
                          borderRadius: "4px",
                          marginBottom: 1
                        }}
                      />
                    );
                  })}
                  {/* Hour label under each bar stack */}
                  <div className="text-xs text-slate-500" style={{ fontSize: 10, marginTop: 3 }}>
                    {hour}
                  </div>
                </div>
              );
            })}
          </div>
          {/* X-axis label (hour) */}
          <div className="text-xs text-slate-600 mt-1">hour</div>
        </div>
        {/* Chart Legend: color box with species label for each species in this session */}
        <div className="flex flex-col gap-2 ml-2">
          {speciesList.map(s => (
            <span key={s} className="flex items-center gap-1 text-xs">
              <span
                style={{
                  display: "inline-block",
                  width: 12,
                  height: 12,
                  background: colorForSpecies(s),
                  borderRadius: 2
                }}
              />
              <span style={{color: "#222", fontWeight: 500}}>{s}</span>
            </span>
          ))}
        </div>
      </div>
    </Card>
  );
}