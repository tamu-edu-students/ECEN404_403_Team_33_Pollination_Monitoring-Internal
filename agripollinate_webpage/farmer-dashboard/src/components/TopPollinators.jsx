import React, { useEffect, useMemo, useState } from 'react'
import Card from './Card'
import insectStore from '../state/insectStore'

// Component shows "Top 3 Pollinators", updating live from global insectStore
export default function TopPollinators({
}) {
  // Subscribe to insectStore for all updates to counts; keep local copy of current store state
  const [storeState, setStoreState] = useState(insectStore.getState())
  useEffect(() => {
    const unsubscribe = insectStore.subscribe(s => {
      setStoreState({ ...s })
    })
    return unsubscribe
  }, [])

  //Log only when storeState changes (not on every render) to verify updates are received correctly
  useEffect(() => {
    console.log('TopPollinators storeState updated:', storeState)
  }, [storeState])

  // Compute and memoize (recompute only when storeState changes) the top 3 pollinators by value/count
  const topList = useMemo(() => {
    return (storeState.pollinators || [])
      .slice()
      .sort((a, b) => b.value - a.value)
      .slice(0, 3)
  }, [storeState])

  const max = Math.max(...topList.map(d => d.value), 1)
  const visualMax = Math.max(max, 4)  // floor to prevent single bar filling entire chart
  const chartHeightPx = 160
  const minBarHeightPx = 14

  return (
    <Card className="col-span-2 row-span-1 bg-white border-2 border-blue-200 rounded-lg shadow-lg p-6">
      {/* Header: Title and update status */}
      <div className="flex items-start justify-between">
        <div>
          <div className="font-semibold text-slate-700">Top 3 Pollinators</div>
          <div className="text-sm text-slate-500 mt-1">Latest counts / activity</div>
        </div>
        <div className="text-sm text-slate-400">Updated just now</div>
      </div>
      {/* Main content area: icon+labels left, bar chart right */}
      <div className="flex items-start gap-6 mt-4">
        {/* Left column: icon, label, count for each top pollinator */}
        <div className="flex flex-col gap-4">
          {topList.map(d => (
            <div key={d.label} className="flex items-center gap-3">
              {/* Species emoji/icon (if present) or bee fallback */}
              <div className="text-3xl">{d.icon ?? '🐝'}</div>
              <div>
                {/* Species name and count */}
                <div className="font-medium">{d.label}</div>
                <div className="text-xs text-slate-400">{d.value}</div>
              </div>
            </div>
          ))}
        </div>
        {/* Right: horizontal bar chart, scales bar height based on count */}
        <div className="flex-1 flex items-end" style={{ height: chartHeightPx }}>
          <div className="w-full flex items-end justify-center gap-4 h-full">
            {topList.map(d => {
              const heightPx = Math.max(
                minBarHeightPx,
                Math.round((d.value / visualMax) * chartHeightPx)
              )
              return (
                <div key={d.label} className="w-16 flex flex-col items-center">
                  <div
                    className="w-full rounded-t-md transition-all duration-500 ease-out"
                    style={{
                      height: `${heightPx}px`,
                      background: d.color || '#60A5FA',
                      minHeight: `${minBarHeightPx}px`,
                      boxShadow: 'inset 0 -6px 12px rgba(0,0,0,0.08)'
                    }}
                    title={`${d.label}: ${d.value}`}
                  />
                  <div className="mt-2 text-xs text-slate-500 text-center">{d.label}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Card>
  )
}