/**
 * Navigation for the Tracker shell.
 *
 * Entries are organised around the user's own things — today, habits,
 * experiments, analytics and settings — never around internal
 * implementation stages. Each entry only needs a path, a label and a one-line
 * description (shown as the link tooltip).
 */

export interface NavigationItem {
  path: string
  label: string
  summary: string
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    path: '/',
    label: 'Обзор',
    summary: 'Оценка дня, серии выполнений, самочувствие, тепловая карта и комментарии совы.',
  },
  {
    path: '/check-in',
    label: 'Итоги дня',
    summary: 'Отметки привычек, оценки и серии, настроение, энергия, сон и заметка дня.',
  },
  {
    path: '/habits',
    label: 'Привычки',
    summary: 'Привычки по сферам: цвета, важность, способ учёта, расписание и архив.',
  },
  {
    path: '/analytics',
    label: 'Аналитика',
    summary: 'Графики привычек и сфер, рекорды и календарь активности.',
  },
  {
    path: '/experiments',
    label: 'Эксперименты',
    summary: 'Личные эксперименты со сравнением показателей до, во время и после.',
  },
  {
    path: '/settings',
    label: 'Настройки',
    summary: 'Резервные копии, экспорт JSON и CSV, проверка и восстановление данных.',
  },
]
