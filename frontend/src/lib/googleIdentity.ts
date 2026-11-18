export interface GoogleCredentialResponse {
  credential?: string;
}

export interface GoogleIdentityClient {
  initialize(options: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }): void;
  renderButton(
    element: HTMLElement,
    options: {
      type: "icon";
      theme: "outline";
      size: "large";
      shape: "square";
      locale: string;
    },
  ): void;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: GoogleIdentityClient;
      };
    };
  }
}

const SCRIPT_URL = "https://accounts.google.com/gsi/client";
let clientPromise: Promise<GoogleIdentityClient> | null = null;

export function loadGoogleIdentityClient(): Promise<GoogleIdentityClient> {
  const loadedClient = window.google?.accounts.id;
  if (loadedClient) return Promise.resolve(loadedClient);
  if (clientPromise) return clientPromise;

  clientPromise = new Promise<GoogleIdentityClient>((resolve, reject) => {
    let script = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_URL}"]`);
    const onLoad = () => {
      const client = window.google?.accounts.id;
      if (client) resolve(client);
      else reject(new Error("Google Identity Services loaded without its API."));
    };
    const onError = () => {
      script?.remove();
      reject(new Error("Google Identity Services could not be loaded."));
    };

    if (!script) {
      script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
    }

    script.addEventListener("load", onLoad, { once: true });
    script.addEventListener("error", onError, { once: true });
    if (!script.isConnected) document.head.appendChild(script);
  }).catch((error: unknown) => {
    clientPromise = null;
    throw error;
  });

  return clientPromise;
}
