import { useEffect } from "react";

import { Shell, useTheme } from "./components/Shell";
import { Frame, Loading } from "./components/ui";
import { AcceptInvitePage, ForgotPasswordPage, SignInPage } from "./pages/AuthPages";
import { DatasetPage } from "./pages/DatasetPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { ExportPage } from "./pages/ExportPage";
import { NewSearchPage } from "./pages/NewSearchPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SearchPage } from "./pages/SearchPage";
import { UsersPage } from "./pages/UsersPage";
import { navigate, useRoute, type Route } from "./lib/router";
import { SessionProvider, useSession } from "./lib/session";

function MessagePage({ title, body }: { title: string; body: string }) {
  return (
    <div className="page page--narrow">
      <Frame className="message">
        <h2>{title}</h2>
        <p className="muted">{body}</p>
        <a className="btn btn-secondary" href="#/">
          Go to datasets
        </a>
      </Frame>
    </div>
  );
}

/** Pages reserved to Administrators and Dataset Administrators (Requirements 3.2). */
const MANAGER_ROUTES: Route["name"][] = ["newSearch", "export", "users"];

function Routed() {
  const route = useRoute();
  const session = useSession();
  useTheme();

  const routeKey = JSON.stringify(route);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [routeKey]);

  // Signed-in users never see the account pages; signed-out users only see them.
  useEffect(() => {
    if (session.mode === "signed-in" && (route.name === "signin" || route.name === "forgot")) {
      navigate("/");
    }
  }, [session.mode, route.name]);

  if (session.mode === "loading") {
    return (
      <div className="auth-screen">
        <Loading label="Starting…" />
      </div>
    );
  }

  if (route.name === "invite") {
    return <AcceptInvitePage token={route.token} />;
  }
  if (route.name === "forgot") {
    return <ForgotPasswordPage />;
  }
  if (route.name === "signin" || session.mode === "signed-out") {
    return <SignInPage />;
  }

  let page;
  if (MANAGER_ROUTES.includes(route.name) && !session.canManage) {
    page = (
      <MessagePage
        title="You don’t have access to this page"
        body="Only Administrators and Dataset Administrators can launch searches, export annotations and manage users. Annotators review candidates in the datasets assigned to them."
      />
    );
  } else {
    switch (route.name) {
      case "datasets":
        page = <DatasetsPage />;
        break;
      case "dataset":
        page = <DatasetPage key={route.datasetId} datasetId={route.datasetId} />;
        break;
      case "newSearch":
        page = <NewSearchPage key={route.datasetId} datasetId={route.datasetId} />;
        break;
      case "search":
        page = <SearchPage key={routeKey} datasetId={route.datasetId} searchId={route.searchId} />;
        break;
      case "review":
        page = <ReviewPage key={routeKey} datasetId={route.datasetId} searchId={route.searchId} />;
        break;
      case "export":
        page = <ExportPage key={routeKey} initialDatasetId={route.datasetId} />;
        break;
      case "users":
        page = <UsersPage />;
        break;
      default:
        page = (
          <MessagePage
            title="Page not found"
            body={`There is no screen at ${route.name === "notFound" ? route.pathname : "this address"}.`}
          />
        );
    }
  }

  return <Shell route={route}>{page}</Shell>;
}

function App() {
  return (
    <SessionProvider>
      <Routed />
    </SessionProvider>
  );
}

export default App;
