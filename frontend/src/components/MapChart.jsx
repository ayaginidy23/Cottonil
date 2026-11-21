// =============================================================================
// MapChart.jsx - "type: map" in an app YAML: one point per Egyptian governorate
// -----------------------------------------------------------------------------
//   x:      column with the governorate name (Arabic or English, as in the data)
//   series: [{key, label, format?}]  - the FIRST series ranks the governorates;
//           every series is shown in the card that opens on click
// Look: satellite background, a small white point + name per governorate, and
// the top governorate in orange. Click a point for its numbers (value, share of
// the total, rank). The Nile Delta is crowded, so at country zoom only the
// biggest names are written; zoom in (or press "Delta & Cairo") to see them all.
// The governorate is placed at its capital city. Names are compared after
// normalising Arabic spelling (أ/إ/ا, ة/ه, ى/ي, "محافظة"), and big cities that
// appear instead of a governorate (طنطا، المنصورة...) map to their governorate.
// Satellite tiles come from Esri World Imagery (needs internet in the browser);
// without internet the points are still drawn on an empty background.
// =============================================================================
import { useState } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { fmt } from '../lib/format.js'
import { useLang } from '../lib/i18n.jsx'

// [lat, lng] of each governorate's capital + its English name
const GOVERNORATES = {
  'القاهره': [30.0444, 31.2357, 'Cairo'], 'الجيزه': [29.987, 31.2118, 'Giza'],
  'الاسكندريه': [31.2001, 29.9187, 'Alexandria'], 'القليوبيه': [30.466, 31.1858, 'Qalyubia'],
  'الشرقيه': [30.5877, 31.502, 'Sharqia'], 'الدقهليه': [31.0409, 31.3785, 'Dakahlia'],
  'الغربيه': [30.7865, 31.0004, 'Gharbia'], 'المنوفيه': [30.5972, 30.9876, 'Monufia'],
  'البحيره': [31.0341, 30.4682, 'Beheira'], 'كفر الشيخ': [31.1107, 30.9388, 'Kafr El Sheikh'],
  'دمياط': [31.4175, 31.8144, 'Damietta'], 'بورسعيد': [31.2653, 32.3019, 'Port Said'],
  'الاسماعيليه': [30.5965, 32.2715, 'Ismailia'], 'السويس': [29.9668, 32.5498, 'Suez'],
  'الفيوم': [29.3084, 30.8428, 'Faiyum'], 'بني سويف': [29.0661, 31.0994, 'Beni Suef'],
  'المنيا': [28.0871, 30.7618, 'Minya'], 'اسيوط': [27.1783, 31.1859, 'Asyut'],
  'سوهاج': [26.5591, 31.6957, 'Sohag'], 'قنا': [26.1551, 32.716, 'Qena'],
  'الاقصر': [25.6872, 32.6396, 'Luxor'], 'اسوان': [24.0889, 32.8998, 'Aswan'],
  'البحر الاحمر': [27.2579, 33.8116, 'Red Sea'], 'الوادي الجديد': [25.439, 30.5586, 'New Valley'],
  'مطروح': [31.3543, 27.2373, 'Matrouh'], 'شمال سيناء': [31.1316, 33.7984, 'North Sinai'],
  'جنوب سيناء': [27.9158, 34.33, 'South Sinai'],
}
// cities / English names that may appear instead of the Arabic governorate name
const ALIASES = {
  'طنطا': 'الغربيه', 'المحله الكبري': 'الغربيه', 'المنصوره': 'الدقهليه', 'الزقازيق': 'الشرقيه',
  'العاشر من رمضان': 'الشرقيه', 'بنها': 'القليوبيه', 'شبرا الخيمه': 'القليوبيه', 'دمنهور': 'البحيره',
  'شبين الكوم': 'المنوفيه', '6 اكتوبر': 'الجيزه', 'السادس من اكتوبر': 'الجيزه', 'الغردقه': 'البحر الاحمر',
  'شرم الشيخ': 'جنوب سيناء', 'العريش': 'شمال سيناء', 'مرسي مطروح': 'مطروح', 'الخارجه': 'الوادي الجديد',
  cairo: 'القاهره', giza: 'الجيزه', alexandria: 'الاسكندريه', qalyubia: 'القليوبيه', sharqia: 'الشرقيه',
  dakahlia: 'الدقهليه', gharbia: 'الغربيه', monufia: 'المنوفيه', beheira: 'البحيره',
  'kafr el sheikh': 'كفر الشيخ', damietta: 'دمياط', 'port said': 'بورسعيد', ismailia: 'الاسماعيليه',
  suez: 'السويس', faiyum: 'الفيوم', fayoum: 'الفيوم', 'beni suef': 'بني سويف', minya: 'المنيا',
  asyut: 'اسيوط', assiut: 'اسيوط', sohag: 'سوهاج', qena: 'قنا', luxor: 'الاقصر', aswan: 'اسوان',
  'red sea': 'البحر الاحمر', 'new valley': 'الوادي الجديد', matrouh: 'مطروح',
  'north sinai': 'شمال سيناء', 'south sinai': 'جنوب سيناء',
}

const EGYPT = [[23.6, 28.6], [31.7, 34.4]]          // the Nile valley + Sinai (where the points are)
const DELTA = [[29.8, 29.75], [31.6, 32.7]]            // Cairo, Giza, the Delta and the canal cities
const LABEL_ALL_ZOOM = 7                              // from this zoom the Delta names are written too
// points that sit almost on top of a neighbour get their name on another side
const LABEL_SIDE = { 'الجيزه': 'bottom', 'القليوبيه': 'top', 'المنوفيه': 'opposite', 'بني سويف': 'opposite' }
const inDelta = (lat, lng) => lat >= DELTA[0][0] && lat <= DELTA[1][0] && lng >= DELTA[0][1] && lng <= DELTA[1][1]

function normalise(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[ً-ْـ]/g, '')
    .replace(/[إأآا]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه')
    .replace(/محافظه/g, '').replace(/governorate/g, '')
    .replace(/\s+/g, ' ').trim()
}

function lookup(name) {
  const n = normalise(name)
  const key = GOVERNORATES[n] ? n : ALIASES[n]
  return key ? GOVERNORATES[key] : null
}

export function locate(name) {
  const g = lookup(name)
  return g ? [g[0], g[1]] : null
}

// keeps the current zoom in React state (labels depend on it)
function ZoomWatcher({ onZoom }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) })
  return null
}

export default function MapChart({ chart }) {
  const { lang, tl } = useLang()
  const ar = lang === 'ar'
  const [map, setMap] = useState(null)
  const [zoom, setZoom] = useState(5)
  const { data = [], x, series = [], format } = chart
  const main = series[0]
  if (!main) return null

  const points = data.map((r) => {
    const n = normalise(r[x])
    const key = GOVERNORATES[n] ? n : ALIASES[n]
    return { row: r, key, g: key ? GOVERNORATES[key] : null, value: Number(r[main.key]) || 0 }
  })
  const placed = points.filter((p) => p.g).sort((a, b) => b.value - a.value)
  const missing = points.filter((p) => !p.g).map((p) => p.row[x]).filter(Boolean)
  const total = placed.reduce((s, p) => s + p.value, 0)
  const name = (p) => (ar ? String(p.row[x]) : p.g[2])
  // draw the biggest last so it is on top
  const drawOrder = [...placed].reverse()

  return (
    <div className="map-wrap">
      <div className="map-box">
        <MapContainer bounds={EGYPT} scrollWheelZoom={false} className="map" attributionControl ref={setMap}>
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution="Tiles &copy; Esri"
            maxZoom={12}
          />
          <ZoomWatcher onZoom={setZoom} />
          {drawOrder.map((p) => {
            const rank = placed.indexOf(p) + 1
            const top = rank === 1
            // whole country: the top name + names outside the crowded Delta; zoomed in: every name
            const showLabel = top || !inDelta(p.g[0], p.g[1]) || zoom >= LABEL_ALL_ZOOM
            const side = LABEL_SIDE[p.key] === 'opposite' ? (ar ? 'right' : 'left') : (LABEL_SIDE[p.key] || (ar ? 'left' : 'right'))
            const offset = { left: [-8, 0], right: [8, 0], top: [0, -8], bottom: [0, 8] }[side]
            return (
              <CircleMarker key={p.row[x]} center={[p.g[0], p.g[1]]} radius={top ? 8 : 6}
                pathOptions={{ color: '#ffffff', weight: 2, fillColor: top ? '#f5a524' : '#ffffff', fillOpacity: 1 }}>
                {showLabel && (
                  <Tooltip permanent direction={side} offset={offset}
                    className={`map-label ${top ? 'top' : ''}`}>
                    {name(p)}
                  </Tooltip>
                )}
                <Popup className="map-popup" closeButton={false}>
                  <div dir={ar ? 'rtl' : 'ltr'}>
                    <div className="map-pop-title">{name(p)}</div>
                    {series.map((s) => (
                      <div key={s.key} className="map-pop-row">
                        <span>{tl(s.label)}</span>
                        <strong>{fmt(p.row[s.key], s.format || format, { compact: false })}</strong>
                      </div>
                    ))}
                    {total > 0 && (
                      <div className="map-pop-row">
                        <span>{ar ? 'النسبة من الإجمالي' : 'Share of total'}</span>
                        <strong>{fmt(p.value / total, 'pct')}</strong>
                      </div>
                    )}
                    <div className="map-pop-rank">
                      {ar ? `المركز ${rank} من ${placed.length}` : `Rank ${rank} of ${placed.length}`}
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            )
          })}
        </MapContainer>
        <div className="map-zoom no-print">
          <button className="chip" onClick={() => map?.flyToBounds(EGYPT, { duration: 0.6 })}>
            {ar ? 'مصر كلها' : 'All Egypt'}
          </button>
          <button className="chip" onClick={() => map?.flyToBounds(DELTA, { duration: 0.6 })}>
            {ar ? 'الدلتا والقاهرة' : 'Delta & Cairo'}
          </button>
        </div>
      </div>
      <div className="muted small">
        {ar ? 'اضغط على أي نقطة تشوف أرقامها. البرتقالي = الأعلى.' : 'Click a point to see its numbers. Orange = the highest.'}
      </div>
      {missing.length > 0 && (
        <div className="muted small">Not on the map (unknown name): {missing.join(', ')}</div>
      )}
    </div>
  )
}
