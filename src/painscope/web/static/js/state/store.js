export const state = {
  profiles: [],
  scans: [],
  activePoll: null,
  savedOpportunities: [],
  onboarding: {
    discover: false,
    configure: false,
    analyze: false,
  },
  form: {
    objective: "pain_points",
    scanType: "pain_points",
    language: "tr",
    profile: "tr",
    useYaml: false,
    yaml: "",
    limitPerSource: 200,
    topN: 20,
  },
};

export function loadSavedState() {
  state.savedOpportunities = readJson("painscope.savedOpportunities", []);
  state.onboarding = {
    ...state.onboarding,
    ...readJson("painscope.onboarding", {}),
  };
}

export function persistSavedOpportunities() {
  localStorage.setItem("painscope.savedOpportunities", JSON.stringify(state.savedOpportunities));
}

export function persistOnboarding() {
  localStorage.setItem("painscope.onboarding", JSON.stringify(state.onboarding));
}

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
