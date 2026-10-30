// =============================================================================
// main.jsx - React entry point: routes + global providers
// =============================================================================
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import AppPage from './pages/AppPage.jsx'
import NotFound from './pages/NotFound.jsx'
import ShopChat from './pages/ShopChat.jsx'
import AnalystChat from './pages/AnalystChat.jsx'
import { FiltersProvider } from './lib/filters.jsx'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <FiltersProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/apps/executive" replace />} />
            {/* One page renders every dashboard app: /apps/sales, /apps/branch_pnl ... */}
            <Route path="/apps/:appId" element={<AppPage />} />
            <Route path="/chat/shop" element={<ShopChat />} />
            <Route path="/chat/analyst" element={<AnalystChat />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </FiltersProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
