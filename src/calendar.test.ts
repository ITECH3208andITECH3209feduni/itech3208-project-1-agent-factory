import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock config — calendar module reads these as plain constants
vi.mock('./config.js', () => ({
  GOOGLE_CALENDAR_KEY_PATH: '/tmp/fake-key.json',
  GOOGLE_CALENDAR_ID: 'test-calendar@group.calendar.google.com',
}));

vi.mock('./logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

// google-auth-library mock — mirrors the telegram.test.ts pattern of mocking
// the underlying client library rather than hitting the network.
const requestMock = vi.hoisted(() => vi.fn());

vi.mock('google-auth-library', () => ({
  JWT: class MockJWT {
    email: string;
    key: string;
    scopes: string[];
    request = requestMock;
    constructor(opts: { email: string; key: string; scopes: string[] }) {
      this.email = opts.email;
      this.key = opts.key;
      this.scopes = opts.scopes;
    }
  },
}));

import fs from 'fs';
import { bookAppointment, isCalendarConfigured } from './calendar.js';

const VALID_KEY = JSON.stringify({
  client_email: 'agent47@vivid-reality-504418-b9.iam.gserviceaccount.com',
  private_key: '-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n',
});

describe('calendar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('isCalendarConfigured', () => {
    it('returns true when key file exists', () => {
      vi.spyOn(fs, 'existsSync').mockReturnValue(true);
      expect(isCalendarConfigured()).toBe(true);
    });

    it('returns false when key file is missing', () => {
      vi.spyOn(fs, 'existsSync').mockReturnValue(false);
      expect(isCalendarConfigured()).toBe(false);
    });
  });

  describe('bookAppointment', () => {
    it('creates an event and returns the event URL on success', async () => {
      vi.spyOn(fs, 'readFileSync').mockReturnValue(VALID_KEY);
      requestMock.mockResolvedValue({
        data: { htmlLink: 'https://calendar.google.com/event?eid=abc123' },
      });

      const result = await bookAppointment({
        summary: 'Consultation with Alice',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'Australia/Sydney',
      });

      expect(result.ok).toBe(true);
      expect(result.eventUrl).toBe(
        'https://calendar.google.com/event?eid=abc123',
      );
      expect(requestMock).toHaveBeenCalledWith(
        expect.objectContaining({
          url: expect.stringContaining(
            encodeURIComponent('test-calendar@group.calendar.google.com'),
          ),
          method: 'POST',
          data: expect.objectContaining({
            summary: 'Consultation with Alice',
            start: {
              dateTime: '2026-08-10T14:00:00',
              timeZone: 'Australia/Sydney',
            },
            end: {
              dateTime: '2026-08-10T14:30:00',
              timeZone: 'Australia/Sydney',
            },
          }),
        }),
      );
    });

    it('includes attendee when attendeeEmail is provided', async () => {
      vi.spyOn(fs, 'readFileSync').mockReturnValue(VALID_KEY);
      requestMock.mockResolvedValue({ data: {} });

      await bookAppointment({
        summary: 'Consultation',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'Australia/Sydney',
        attendeeEmail: 'client@example.com',
      });

      expect(requestMock).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            attendees: [{ email: 'client@example.com' }],
          }),
        }),
      );
    });

    it('omits attendees field when no attendeeEmail given', async () => {
      vi.spyOn(fs, 'readFileSync').mockReturnValue(VALID_KEY);
      requestMock.mockResolvedValue({ data: {} });

      await bookAppointment({
        summary: 'Consultation',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'Australia/Sydney',
      });

      expect(requestMock).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ attendees: undefined }),
        }),
      );
    });

    it('returns an error result when the key file is missing required fields', async () => {
      vi.spyOn(fs, 'readFileSync').mockReturnValue(
        JSON.stringify({ type: 'service_account' }),
      );

      const result = await bookAppointment({
        summary: 'Test',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'UTC',
      });

      expect(result.ok).toBe(false);
      expect(result.error).toMatch(/client_email\/private_key/);
      expect(requestMock).not.toHaveBeenCalled();
    });

    it('returns an error result when the key file cannot be read', async () => {
      vi.spyOn(fs, 'readFileSync').mockImplementation(() => {
        throw new Error('ENOENT');
      });

      const result = await bookAppointment({
        summary: 'Test',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'UTC',
      });

      expect(result.ok).toBe(false);
      expect(result.error).toBe('Calendar key file could not be read');
    });

    it('returns an error result when the Calendar API call fails', async () => {
      vi.spyOn(fs, 'readFileSync').mockReturnValue(VALID_KEY);
      requestMock.mockRejectedValue(new Error('403 Forbidden'));

      const result = await bookAppointment({
        summary: 'Test',
        startIso: '2026-08-10T14:00:00',
        endIso: '2026-08-10T14:30:00',
        timezone: 'UTC',
      });

      expect(result.ok).toBe(false);
      expect(result.error).toBe('403 Forbidden');
    });
  });
});
