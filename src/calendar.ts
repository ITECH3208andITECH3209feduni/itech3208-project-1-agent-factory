import fs from 'fs';

import { JWT } from 'google-auth-library';

import { GOOGLE_CALENDAR_ID, GOOGLE_CALENDAR_KEY_PATH } from './config.js';
import { logger } from './logger.js';

// Appointment booking (Epic 15 / PROJ-219). Runs on the HOST process only —
// the service account key never gets mounted into agent containers (see
// container-runner.ts's .env shadowing). Agents request bookings via the
// book_appointment IPC task (container/agent-runner/src/ipc-mcp-stdio.ts),
// which src/ipc.ts turns into a call to bookAppointment() below.

const CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar.events'];

export interface BookAppointmentInput {
  summary: string;
  /** ISO 8601 datetime, e.g. "2026-08-10T14:00:00" */
  startIso: string;
  /** ISO 8601 datetime, e.g. "2026-08-10T14:30:00" */
  endIso: string;
  description?: string;
  attendeeEmail?: string;
  timezone: string;
}

export interface BookAppointmentResult {
  ok: boolean;
  eventUrl?: string;
  error?: string;
}

interface ServiceAccountKey {
  client_email?: string;
  private_key?: string;
}

/** True if calendar env vars are set and the key file exists on disk. */
export function isCalendarConfigured(): boolean {
  return Boolean(
    GOOGLE_CALENDAR_KEY_PATH &&
    GOOGLE_CALENDAR_ID &&
    fs.existsSync(GOOGLE_CALENDAR_KEY_PATH),
  );
}

function loadServiceAccountKey(): ServiceAccountKey | null {
  try {
    const raw = fs.readFileSync(GOOGLE_CALENDAR_KEY_PATH, 'utf-8');
    return JSON.parse(raw) as ServiceAccountKey;
  } catch (err) {
    logger.error(
      { err, path: GOOGLE_CALENDAR_KEY_PATH },
      'Failed to read Google Calendar service account key file',
    );
    return null;
  }
}

/**
 * Create an event on the configured Google Calendar. The target calendar
 * must have been shared with the service account's client_email (permission:
 * "Make changes to events") — see docs/setup or the PROJ-219 ticket comment
 * for the exact steps.
 */
export async function bookAppointment(
  input: BookAppointmentInput,
): Promise<BookAppointmentResult> {
  if (!GOOGLE_CALENDAR_KEY_PATH || !GOOGLE_CALENDAR_ID) {
    return {
      ok: false,
      error:
        'Calendar not configured — set GOOGLE_CALENDAR_KEY_PATH and GOOGLE_CALENDAR_ID in .env',
    };
  }

  const keyData = loadServiceAccountKey();
  if (!keyData) {
    return { ok: false, error: 'Calendar key file could not be read' };
  }
  if (!keyData.client_email || !keyData.private_key) {
    return {
      ok: false,
      error: 'Calendar key file is missing client_email/private_key',
    };
  }

  try {
    const client = new JWT({
      email: keyData.client_email,
      key: keyData.private_key,
      scopes: CALENDAR_SCOPES,
    });

    const url = `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(GOOGLE_CALENDAR_ID)}/events`;

    const res = await client.request<{ htmlLink?: string }>({
      url,
      method: 'POST',
      data: {
        summary: input.summary,
        description: input.description,
        start: { dateTime: input.startIso, timeZone: input.timezone },
        end: { dateTime: input.endIso, timeZone: input.timezone },
        attendees: input.attendeeEmail
          ? [{ email: input.attendeeEmail }]
          : undefined,
      },
    });

    logger.info(
      { summary: input.summary, start: input.startIso },
      'Calendar event created',
    );
    return { ok: true, eventUrl: res.data?.htmlLink };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logger.error({ err }, 'Failed to create calendar event');
    return { ok: false, error: message };
  }
}
