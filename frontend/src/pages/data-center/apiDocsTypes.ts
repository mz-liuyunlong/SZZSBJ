export type ApiMethod = "GET" | "POST" | "PUT" | "DELETE";

export interface ApiFieldSpec {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export interface ApiDocItem {
  id: string;
  moduleKey: string;
  moduleName: string;
  levelName: string;
  levelDesc: string;
  method: ApiMethod;
  title: string;
  path: string;
  purpose: string;
  requestMode: string;
  successReturn: string;
  scenario: string;
  authScope: string;
  queryParams: ApiFieldSpec[];
  bodyParams: ApiFieldSpec[];
  returnFields: ApiFieldSpec[];
  requestExample: Record<string, unknown>;
  responseExample: Record<string, unknown>;
}

export interface ApiDocLevel {
  name: string;
  desc: string;
  apis: ApiDocItem[];
}

export interface ApiDocModule {
  key: string;
  name: string;
  icon: string;
  desc: string;
  levels: ApiDocLevel[];
}

export const flattenApiDocs = (modules: ApiDocModule[]) => modules.flatMap((module) => module.levels.flatMap((level) => level.apis));

export const filterApiDocs = (modules: ApiDocModule[], keyword: string) => {
  const normalized = keyword.trim().toLocaleLowerCase();
  if (!normalized) return modules;

  return modules
    .map((module) => ({
      ...module,
      levels: module.levels
        .map((level) => ({
          ...level,
          apis: level.apis.filter((api) => [
            module.name,
            level.name,
            api.method,
            api.title,
            api.path,
            api.purpose,
            api.authScope,
          ].some((value) => value.toLocaleLowerCase().includes(normalized))),
        }))
        .filter((level) => level.apis.length > 0),
    }))
    .filter((module) => module.levels.length > 0);
};

export const getApiCount = (module: ApiDocModule) => module.levels.reduce((total, level) => total + level.apis.length, 0);

export const getMethodColor = (method: ApiMethod) => {
  const colors: Record<ApiMethod, string> = {
    GET: "blue",
    POST: "green",
    PUT: "orange",
    DELETE: "red",
  };
  return colors[method];
};
