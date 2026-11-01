// =============================================================================
// MapChart.jsx - "type: map" in an app YAML: one bubble per Egyptian governorate
// -----------------------------------------------------------------------------
//   x:      column with the governorate name (Arabic or English, as in the data)
//   series: [{key, label, format?}]  - the FIRST series sets the bubble size,
//           every series is shown in the popup
// The governorate is placed at its capital city. Names are compared after
// normalising Arabic spelling (أ/إ/ا, ة/ه, ى/ي, "محافظة"), and big cities that
// appear instead of a governorate (طنطا، المنصورة...) map to their governorate.
// Map tiles come from OpenStreetMap (needs internet in the browser); without
// internet the bubbles are still drawn on an empty background.
// =============================================================================
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { fmt } from '../lib/format.js'
import { SERIES } from '../lib/colors.js'
import { useLang } from '../lib/i18n.jsx'

// [lat, lng] of each governorate's capital
const GOVERNORATES = {
  'القاهره': [30.0444, 31.2357], 'الجيزه': [29.987, 31.2118], 'الاسكندريه': [31.2001, 29.9187],
  'القليوبيه': [30.466, 31.1858], 'الشرقيه': [30.5877, 31.502], 'الدقهليه': [31.0409, 31.3785],
  'الغربيه': [30.7865, 31.0004], 'المنوفيه': [30.5972, 30.9876], 'البحيره': [31.0341, 30.4682],
  'كفر الشيخ': [31.1107, 30.9388], 'دمياط': [31.4175, 31.8144], 'بورسعيد': [31.2653, 32.3019],
  'الاسماعيليه': [30.5965, 32.2715], 'السويس': [29.9668, 32.5498], 'الفيوم': [29.3084, 30.8428],
  'بني سويف': [29.0661, 31.0994], 'المنيا': [28.0871, 30.7618], 'اسيوط': [27.1783, 31.1859],
  'سوهاج': [26.5591, 31.6957], 'قنا': [26.1551, 32.716], 'الاقصر': [25.6872, 32.6396],
  'اسوان': [24.0889, 32.8998], 'البحر الاحمر': [27.2579, 33.8116], 'الوادي الجديد': [25.439, 30.5586],
  'مطروح': [31.3543, 27.2373], 'شمال سيناء': [31.1316, 33.7984], 'جنوب سيناء': [27.9158, 34.33],
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

function normalise(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[ً-ْـ]/g, '')
    .replace(/[إأآا]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه')
    .replace(/محافظه/g, '').replace(/governorate/g, '')
    .replace(/\s+/g, ' ').trim()
}

export function locate(name) {
  const n = normalise(name)
  const key = GOVERNORATES[n] ? n : ALIASES[n]
  return key ? GOVERNORATES[key] : null
}

export default function MapChart({ chart }) {
  const { tl } = useLang()
  const { data = [], x, series = [], format } = chart
  const main = series[0]
  if (!main) return null
  const points = data
    .map((r) => ({ row: r, pos: locate(r[x]), value: Number(r[main.key]) || 0 }))
  const placed = points.filter((p) => p.pos)
  const missing = points.filter((p) => !p.pos).map((p) => p.row[x]).filter(Boolean)
  const max = Math.max(...placed.map((p) => Math.abs(p.value)), 1)

  return (
    <div className="map-wrap">
      <MapContainer center={[27.2, 30.8]} zoom={5} scrollWheelZoom={false} className="map" attributionControl>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        {placed.map((p) => (
          <CircleMarker key={p.row[x]} center={p.pos}
            radius={6 + 24 * Math.sqrt(Math.abs(p.value) / max)}      // area grows with the value
            pathOptions={{ color: SERIES[0], fillColor: SERIES[0], fillOpacity: 0.45, weight: 1.5 }}>
            <Tooltip direction="top">
              <div dir="auto"><strong>{p.row[x]}</strong></div>
              {series.map((s) => (
                <div key={s.key}>{tl(s.label)}: {fmt(p.row[s.key], s.format || format, { compact: false })}</div>
              ))}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      {missing.length > 0 && (
        <div className="muted small">Not on the map (unknown name): {missing.join(', ')}</div>
      )}
    </div>
  )
}
