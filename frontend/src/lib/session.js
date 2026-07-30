// Who the current visitor is within a collective, keyed per collective so
// switching between groups (or demo roles) doesn't leak identity across.
const key = (collectiveId) => `evident:m:${collectiveId}`;

export const getSessionMember = (collectiveId) =>
  sessionStorage.getItem(key(collectiveId)) || null;

export const setSessionMember = (collectiveId, memberId) => {
  if (memberId) sessionStorage.setItem(key(collectiveId), memberId);
  else sessionStorage.removeItem(key(collectiveId));
};

// The signed token from a personal link. This is the actual credential — the
// member id above only says who the UI thinks you are, and the server no longer
// takes its word for it. sessionStorage, not localStorage, so closing the tab
// ends the session rather than leaving a treasury credential on a shared laptop.
const tokenKey = (collectiveId) => `evident:t:${collectiveId}`;

export const getSessionToken = (collectiveId) =>
  sessionStorage.getItem(tokenKey(collectiveId)) || null;

export const setSessionToken = (collectiveId, token) => {
  if (token) sessionStorage.setItem(tokenKey(collectiveId), token);
  else sessionStorage.removeItem(tokenKey(collectiveId));
};
