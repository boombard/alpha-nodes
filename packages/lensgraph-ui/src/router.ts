/**
 * Hash routing (works on file://): `#/`, `#/graph`, `#/candidate/<id>`; the summary and candidate
 * routes carry the candidate list's state in the hash query (see `listState.ts`).
 */
import { useEffect, useState } from "react";
import { EMPTY_LIST, listFromQuery, listToQuery, type ListState } from "./listState";

/** A parsed location. */
export type Route =
  | { page: "summary"; list: ListState }
  | { page: "graph" }
  | { page: "candidate"; id: string; list: ListState };

/** Parse a `location.hash` into a route (unknown hashes mean the summary). */
export function parseHash(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?", 2);
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "graph") return { page: "graph" };
  if (parts[0] === "candidate" && parts[1]) return { page: "candidate", id: parts[1], list: listFromQuery(query) };
  return { page: "summary", list: listFromQuery(query) };
}

/** The list state carried by a route (empty on the graph page). */
export function routeList(route: Route): ListState {
  return route.page === "graph" ? EMPTY_LIST : route.list;
}

function withQuery(path: string, list: ListState): string {
  const q = listToQuery(list);
  return q ? `${path}?${q}` : path;
}

/** Href of the summary with list state. */
export function summaryHref(list: ListState = EMPTY_LIST): string {
  return withQuery("#/", list);
}

/** Href for a candidate page, keeping the list state so Back/Previous/Next follow the same list. */
export function candidateHref(id: string, list: ListState = EMPTY_LIST): string {
  return withQuery(`#/candidate/${encodeURIComponent(id)}`, list);
}

/** Change the hash without adding a history entry (for list state edits such as typing in search). */
export function replaceHash(href: string): void {
  window.location.replace(href);
}

/** The current route, following `hashchange`. */
export function useRoute(): Route {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return parseHash(hash);
}
