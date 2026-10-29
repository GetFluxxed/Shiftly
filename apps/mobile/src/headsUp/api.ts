export type HeadsUp = {
  message: string;
  updatedAt: string | null;
};

export const headsUpPath = '/heads-up';

export const headsUpSaveUncertain = "We couldn't confirm this update. Refresh Heads Up before trying again to check whether it was saved.";
