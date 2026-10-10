import axios from "axios";
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || "/api" });
api.interceptors.request.use(c => { const t = localStorage.getItem("access"); if (t) c.headers.Authorization = `Bearer ${t}`; return c; });
api.interceptors.response.use(r => r, async e => {
  const o = e.config, rf = localStorage.getItem("refresh");
  const isAuthEndpoint = o?.url?.includes("/auth/login/") || o?.url?.includes("/auth/refresh/");
  if (e.response?.status === 401 && rf && !o?._retry && !isAuthEndpoint) {
    o._retry = true;
    try {
      const { data } = await axios.post(`${api.defaults.baseURL}/auth/refresh/`, { refresh: rf });
      localStorage.setItem("access", data.access);
      o.headers = o.headers || {};
      o.headers.Authorization = `Bearer ${data.access}`;
      return api(o);
    } catch {
      localStorage.clear();
      window.location.href = "/login";
    }
  }
  return Promise.reject(e);
});
export const errMsg = e => {
  if (e?.response?.data?.detail) return e.response.data.detail;
  if (typeof e?.response?.data === "string") return e.response.data;
  if (e?.response?.data && typeof e.response.data === "object") {
    return Object.values(e.response.data).flat().join(" ");
  }
  return e?.message || "Something went wrong. Please try again.";
};
export const inr = v => "₹" + Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 });  // display only
export const list = d => d?.results ?? d ?? [];
export default api;
