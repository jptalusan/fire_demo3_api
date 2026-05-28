import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { LoginScreen } from "./components/LoginScreen";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { JobsProvider } from "./context/JobsContext";
import { Loader2 } from "lucide-react";
import "./index.css";

function Gate() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        Loading…
      </div>
    );
  }
  // JobsProvider mounts only once authenticated, so its poll loop runs with a
  // valid session and resumes any in-flight jobs after a page refresh.
  return user ? (
    <JobsProvider>
      <App />
    </JobsProvider>
  ) : (
    <LoginScreen />
  );
}

createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <Gate />
  </AuthProvider>
);
