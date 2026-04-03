// const BACKEND_API: string = "http://localhost:8000";
const BACKEND_API: string = "https://varunchatbot.onrender.com";

/** FastAPI often returns { detail: string | ValidationError[] } */
export async function parseApiError(res: Response): Promise<string> {
    try {
        const data = await res.json();
        if (typeof data.detail === "string") return data.detail;
        if (Array.isArray(data.detail))
            return data.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join(" ");
        if (data.detail != null) return String(data.detail);
        return res.statusText || "Request failed";
    } catch {
        return res.statusText || "Request failed";
    }
}

export default BACKEND_API;
