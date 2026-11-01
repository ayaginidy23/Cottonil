// =============================================================================
// main.jsx - React entry point: routes + global providers
// -----------------------------------------------------------------------------
// Pages inside <Layout> have the sidebar and the filter bar.
// /print/... pages are bilingual documents made for "Save as PDF" (no sidebar).
// =============================================================================
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import AppPage from './pages/AppPage.jsx'
import NotFound from './pages/NotFound.jsx'
import ShopChat from './pages/ShopChat.jsx'
import AnalystChat from './pages/AnalystChat.jsx'
import InsightsPage from './pages/InsightsPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import SecurityPage from './pages/SecurityPage.jsx'
import OffersPage from './pages/OffersPage.jsx'
import ProductsPage from './pages/ProductsPage.jsx'
import ProductPage from './pages/ProductPage.jsx'
import SimulatorPage from './pages/SimulatorPage.jsx'
import QuotePrint from './pages/QuotePrint.jsx'
import ReportPrint from './pages/ReportPrint.jsx'
import { FiltersProvider } from './lib/filters.jsx'
import { LangProvider } from './lib/i18n.jsx'
import './styles.css'

// No <React.StrictMode>: in development it runs every effect twice, which sent
// every dashboard request to the API twice and made pages slower.
ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <LangProvider>
      <FiltersProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/apps/executive" replace />} />
            {/* One page renders every dashboard app: /apps/sales, /apps/branch_pnl ... */}
            <Route path="/apps/:appId" element={<AppPage />} />
            <Route path="/products" element={<ProductsPage />} />
            <Route path="/products/:productId" element={<ProductPage />} />
            <Route path="/simulator" element={<SimulatorPage />} />
            <Route path="/chat/shop" element={<ShopChat />} />
            <Route path="/chat/analyst" element={<AnalystChat />} />
            <Route path="/ai/insights" element={<InsightsPage />} />
            <Route path="/ai/reports" element={<ReportsPage />} />
            <Route path="/ai/security" element={<SecurityPage />} />
            <Route path="/ai/offers" element={<OffersPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
          <Route path="/print/quote/:quoteId" element={<QuotePrint />} />
          <Route path="/print/report/:reportId" element={<ReportPrint />} />
        </Routes>
      </FiltersProvider>
    </LangProvider>
  </BrowserRouter>,
)
