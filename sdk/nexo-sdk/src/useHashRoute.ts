import { useCallback, useEffect, useState } from "react";

/**
 * Simple hash-based client-side routing for Nexo apps.
 *
 * Returns the current hash route and a navigate function.
 * Routes are hash fragments: "#/expenses" -> "/expenses", "#/" -> "/".
 *
 * Usage:
 *   const [route, navigate] = useHashRoute();
 *   if (route === "/expenses") return <ExpensesPage />;
 *   navigate("/expenses"); // changes hash
 */
export function useHashRoute(): [string, (path: string) => void] {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || "/");

  useEffect(() => {
    function onHashChange() {
      setRoute(window.location.hash.slice(1) || "/");
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((path: string) => {
    window.location.hash = path;
  }, []);

  return [route, navigate];
}
