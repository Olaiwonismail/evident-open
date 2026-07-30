// Who the current visitor is within a collective, keyed per collective so
// switching between groups (or demo roles) doesn't leak identity across.
const key = (collectiveId) => `evident:m:${collectiveId}`;

export const getSessionMember = (collectiveId) =>
  sessionStorage.getItem(key(collectiveId)) || null;

export const setSessionMember = (collectiveId, memberId) => {
  if (memberId) sessionStorage.setItem(key(collectiveId), memberId);
  else sessionStorage.removeItem(key(collectiveId));
};
