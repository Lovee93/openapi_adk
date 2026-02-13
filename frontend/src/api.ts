
// Real API Service connected to Python Backend

export interface AuthField {
  name: string;
  label: string;
  type: "text" | "password";
  required?: boolean;
}

export interface AuthRequirements {
  scheme_name: string;
  type: string;
  description: string;
  fields: AuthField[];
  flows?: string[];
  authorizationUrl?: string;
  tokenUrl?: string;
  key_name?: string;
  key_in?: string;
}

export interface AnalyzeResponse {
    session_id: string;
    requirements: AuthRequirements;
}

export const analyzeSpec = async (specStr: string): Promise<AnalyzeResponse> => {
    const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ spec_content: specStr }),
    });

    if (!response.ok) {
        throw new Error(`Analyze failed: ${response.statusText}`);
    }

    return response.json();
};

export const initAgent = async (sessionId: string, credentials: any): Promise<boolean> => {
    const response = await fetch('/api/init_agent', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId, credentials: credentials }),
    });

    if (!response.ok) {
        throw new Error(`Init failed: ${response.statusText}`);
    }
    
    return true;
};

export const sendMessage = async (sessionId: string, message: string): Promise<{response: string, auth_url?: string}> => {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId, message: message }),
    });

    if (!response.ok) {
        throw new Error(`Chat failed: ${response.statusText}`);
    }

    return response.json();
};

export const authCallback = async (sessionId: string, code: string, state: string): Promise<boolean> => {
    const response = await fetch(`/api/auth_callback?session_id=${sessionId}&code=${code}&state=${state}`);
    if (!response.ok) {
        throw new Error(`Auth callback failed: ${response.statusText}`);
    }
    return true;
};
