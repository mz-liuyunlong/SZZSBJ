/** Public frontend-only credentials for UI verification; these are not secrets or real authentication. */
export const MOCK_USERNAME = "admin";
export const MOCK_PASSWORD = "admin";

export const isValidMockLogin = (username: string, password: string) =>
  username === MOCK_USERNAME && password === MOCK_PASSWORD;
