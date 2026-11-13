import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import { auth } from "./api";
import Layout from "./components/Layout";
import { SessionProvider } from "./session";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Hosts from "./pages/Hosts";
import HostDetail from "./pages/HostDetail";
import Alerts from "./pages/Alerts";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

function Protected() {
  return auth.token ? <SessionProvider><Layout /></SessionProvider> : <Navigate to="/login" replace />;
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Protected />}>
          <Route path="/" element={<Overview />} />
          <Route path="/hosts" element={<Hosts />} />
          <Route path="/hosts/:id" element={<HostDetail />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
