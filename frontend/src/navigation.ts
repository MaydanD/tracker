/**
 * Navigation for the Tracker shell.
 *
 * Every entry exists now so the shell is stable; each screen is filled in by the
 * stage noted in `plannedIn` (see PROJECT-SPEC.md section 25).
 */

export interface NavigationItem {
  path: string
  label: string
  summary: string
  plannedIn: string
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    path: '/',
    label: 'Dashboard',
    summary: 'Day score, streaks, state summary, heatmap and owl commentary.',
    plannedIn: 'Stage 6',
  },
  {
    path: '/check-in',
    label: 'Check-in',
    summary: 'The fast daily entry flow for habit completions and daily state.',
    plannedIn: 'Stage 3',
  },
  {
    path: '/calendar',
    label: 'Calendar',
    summary: 'Monthly view with day detail, plus a GitHub-style yearly heatmap.',
    plannedIn: 'Stage 6',
  },
  {
    path: '/habits',
    label: 'Habits',
    summary: 'Areas, habits, weights, schedules and quantity configuration.',
    plannedIn: 'Stage 2',
  },
  {
    path: '/insights',
    label: 'Insights',
    summary: 'Relationships discovered in your data, with evidence and lag.',
    plannedIn: 'Stage 8',
  },
  {
    path: '/experiments',
    label: 'Experiments',
    summary: 'Temporary self-experiments with before/during/after comparison.',
    plannedIn: 'Stage 10',
  },
  {
    path: '/records',
    label: 'Records',
    summary: 'Personal records, achievements and failure-streak summaries.',
    plannedIn: 'Stage 11',
  },
  {
    path: '/settings',
    label: 'Settings',
    summary: 'Local data location, backups, Excel export and restore.',
    plannedIn: 'Stage 12',
  },
]
