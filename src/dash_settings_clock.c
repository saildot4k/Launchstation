#include "dash_internal.h"
#include "main_title.h"
#include "init.h"
#include "dash_settings_clock.h"
#ifndef NITEMS
#define NITEMS(a) ((int)(sizeof(a) / sizeof((a)[0])))
#endif

/* Clamp fields to the local-time portion of the RTC range, including DST. */
static void clockFieldLimits(int value[6], const int minimum[6], const int maximum[6], int low[6], int high[6])
{
	static const int base_low[] = {0, 1, 1, 0, 0, 0};
	int base_high[] = {0, 12, 31, 23, 59, 59};
	int at_min = 1, at_max = 1;
	for (int i = 0; i < 6; i++) {
		if (i == 2) base_high[2] = dashClockDaysInMonth(value[0], value[1]);
		low[i] = at_min ? minimum[i] : base_low[i];
		high[i] = at_max ? maximum[i] : base_high[i];
		if (value[i] < low[i]) value[i] = low[i];
		if (value[i] > high[i]) value[i] = high[i];
		at_min &= value[i] == minimum[i];
		at_max &= value[i] == maximum[i];
	}
}

/* Keep all edits local until Apply, including preferences and AM/PM. */
static int editClockDateTime(int fields[6], MenuClockSettings *settings)
{
	static const char *const labels[] = {"Year", "Month", "Day", "Hour", "Minute", "Second", "AM/PM",
	                                      "Time zone (UTC)", "Daylight saving", "Hour format"};
	int minimum[6], maximum[6], low[6], high[6];
	int value[6], sel = 0, i, accepted = 0;
	MenuClockSettings choice = *settings;
	char description[80];
	float open = 0.0f, sx = 0.0f, sy = 0.0f, sw = 0.0f;
	const float w = 528.0f, h = 324.0f;
	const float x = (DASH_VW - w) * 0.5f, y = (DASH_VH - h) * 0.5f;
	/* Reserve the seven-field layout even when AM/PM is hidden. */
	const float bw = 56.0f, gap = 8.0f;
	const float bx0 = x + (w - (7 * bw + 6 * gap)) * 0.5f;
	const float by = y + 88, preferences_y = y + 186;
	DashInput in;

	memcpy(value, fields, sizeof(value));
	dashClockManualLimitsForSettings(minimum, maximum, &choice);
	clockFieldLimits(value, minimum, maximum, low, high);
	dashInputFlush();
	while (1) {
		int step = 0, shoulders;
		float dt, oe, target_x, target_y, target_w;

		dashInputPoll(&in);
		if (in.pressed & (DASH_IN_BACK | DASH_IN_MENU)) break;
		if (in.pressed & (DASH_IN_LEFT | DASH_IN_RIGHT)) {
			int direction = (in.pressed & DASH_IN_LEFT) ? -1 : 1;
			do { sel = (sel + direction + 10) % 10; } while (sel == 6 && !choice.use_12h);
			dashSoundPlay(DASH_SND_CURSOR);
		}
		if (in.pressed & DASH_IN_UP) step = 1;
		if (in.pressed & DASH_IN_DOWN) step = -1;
		shoulders = in.pressed | dashInputShoulderRepeat();
		if (shoulders & (DASH_IN_R1 | DASH_IN_R2)) step = 10;
		if (shoulders & (DASH_IN_L1 | DASH_IN_L2)) step = -10;
		if (step) {
			if (sel < 6) {
				if (sel == 3 && choice.use_12h) {
					int hour = value[3] % 12;
					int next = ((hour ? hour : 12) - 1 + step) % 12;
					if (next < 0) next += 12;
					value[3] = ((next + 1) % 12) + (value[3] >= 12 ? 12 : 0);
				} else {
					int range = high[sel] - low[sel] + 1;
					int next = (value[sel] - low[sel] + step) % range;
					if (next < 0) next += range;
					value[sel] = low[sel] + next;
				}
			} else if (sel == 6) {
				value[3] = (value[3] + 12) % 24;
			} else if (sel == 7) {
				/* Offer whole-hour offsets. Preserve a saved fractional offset
				 * until this field is edited, then move in the chosen direction. */
				int offset = choice.timezone_minutes + 720;
				int next = offset / 60;
				if (step < 0 && offset % 60) next++;
				next = (next + step) % 27;
				if (next < 0) next += 27;
				choice.timezone_minutes = next * 60 - 720;
			} else if (sel == 8) {
				choice.daylight_saving = !choice.daylight_saving;
			} else {
				choice.use_12h = !choice.use_12h;
			}
			dashClockManualLimitsForSettings(minimum, maximum, &choice);
			clockFieldLimits(value, minimum, maximum, low, high);
			dashSoundPlay(DASH_SND_CURSOR);
		}
		if (in.pressed & DASH_IN_OK) { accepted = 1; break; }
		target_x = sel < 7 ? bx0 + sel * (bw + gap) : x + 24 + (sel - 7) * 164;
		target_y = sel < 7 ? by : preferences_y;
		target_w = sel < 7 ? bw : 152;
		if (!sw) { sx = target_x; sy = target_y; sw = target_w; }
		dt = dashVisualUpdate();
		open = dashApproach(open, 1.0f, 16.0f * dashAnimSpeed(), dt);
		sx = dashApproach(sx, target_x, 22.0f * dashAnimSpeed(), dt);
		sy = dashApproach(sy, target_y, 22.0f * dashAnimSpeed(), dt);
		sw = dashApproach(sw, target_w, 22.0f * dashAnimSpeed(), dt);
		oe = dashEaseOutCubic(open);
		snprintf(description, sizeof(description), "Local date and time (%d-%d). Apply also saves system preferences.", minimum[0], maximum[0]);
		dashRenderScene();
		dashModalBackdrop(oe);
		dashGfxPushAlpha(oe);
		dashGfxPushOffset(0, 18.0f * (1.0f - oe));
		dashModalPanel(x, y, w, h, oe);
		dashIcon(DI_CLOCK, x + 24, y + 18, 22, DASH_C_ACCENT);
		dashTextS(x + 56, y + 18, "Set PS2 Clock", DASH_FS_LABEL, DASH_C_TEXT);
		dashTextFit(x + 24, y + 48, w - 48, description, DASH_FS_CAPTION, DASH_C_TEXT3);
		dashDrawSelection(sx, sy, sw, 44, 10, 1.0f);
		for (i = 0; i < 10; i++) {
			char text[20];
			float bx = i < 7 ? bx0 + i * (bw + gap) : x + 24 + (i - 7) * 164;
			float row_y = i < 7 ? by : preferences_y;
			float box_w = i < 7 ? bw : 152;
			int number;
			if (i == 6 && !choice.use_12h) continue;
			dashTextCenter(bx + box_w * 0.5f, row_y + 50, labels[i], DASH_FS_CAPTION, DASH_C_TEXT3);
			if (i != sel) dashPanel(bx, row_y, box_w, 44, 10, DC(255, 255, 255, 16));
			if (i < 6) {
				number = value[i];
				if (i == 3 && choice.use_12h) number = value[3] % 12 ? value[3] % 12 : 12;
				snprintf(text, sizeof(text), i == 0 ? "%04d" : "%02d", number);
			} else if (i == 6) {
				snprintf(text, sizeof(text), "%s", value[3] >= 12 ? "PM" : "AM");
			} else if (i == 7) {
				number = abs(choice.timezone_minutes);
				snprintf(text, sizeof(text), "%c%02d:%02d", choice.timezone_minutes < 0 ? '-' : '+', number / 60, number % 60);
			} else {
				snprintf(text, sizeof(text), "%s", i == 8 ? (choice.daylight_saving ? "On (+1h)" : "Off") :
				         (choice.use_12h ? "12-hour" : "24-hour"));
			}
			dashTextCenter(bx + box_w * 0.5f, row_y + 10, text, DASH_FS_LABEL, dashItemColor(i == sel));
			if (i < 5) dashTextCenter(bx + bw + gap * 0.5f, row_y + 10, i < 2 ? "-" : i == 2 ? "" : ":", DASH_FS_LABEL, DASH_C_TEXT2);
			if (i == sel) {
				dashTextCenter(bx + box_w * 0.5f, row_y - 20, "+", DASH_FS_BODY, DASH_C_ACCENT);
				/* Leave ten pixels after the 12 px field label before the minus cue. */
				dashTextCenter(bx + box_w * 0.5f, row_y + 72, "-", DASH_FS_BODY, DASH_C_ACCENT);
			}
		}
		{
			float field_w = dashButtonWidth(DI_BTN_LEFT, NULL) + 2 + dashButtonWidth(DI_BTN_RIGHT, NULL) + 4 +
			                dashTextWidth("Field", DASH_FS_SMALL);
			float change_w = dashButtonWidth(DI_BTN_UP, NULL) + 2 + dashButtonWidth(DI_BTN_DOWN, NULL) + 4 +
			                 dashTextWidth("Change", DASH_FS_SMALL);
			float step_w = dashButtonWidth(-1, "L1") + 2 + dashButtonWidth(-1, "R1") + 4 +
			               dashTextWidth("10", DASH_FS_SMALL);
			float apply_w = dashButtonWidth(dashOkIcon(), NULL) + 8 + dashTextWidth("Apply", DASH_FS_SMALL);
			float cancel_w = dashButtonWidth(dashBackIcon(), NULL) + 8 + dashTextWidth("Cancel", DASH_FS_SMALL);
			/* Include the three group gaps and the Apply/Cancel gap used below. */
			float hints_w = field_w + change_w + step_w + 3 * 12 + apply_w + 24 + cancel_w;
			float hx = x + (w - hints_w) * 0.5f, hy = y + h - 36;

			hx += dashDrawButton(hx, hy, DI_BTN_LEFT, NULL) + 2;
			hx += dashDrawButton(hx, hy, DI_BTN_RIGHT, NULL) + 4;
			hx = dashTextS(hx, hy + 4.5f, "Field", DASH_FS_SMALL, DASH_C_TEXT2) + 12;
			hx += dashDrawButton(hx, hy, DI_BTN_UP, NULL) + 2;
			hx += dashDrawButton(hx, hy, DI_BTN_DOWN, NULL) + 4;
			hx = dashTextS(hx, hy + 4.5f, "Change", DASH_FS_SMALL, DASH_C_TEXT2) + 12;
			hx += dashDrawButton(hx, hy, -1, "L1") + 2;
			hx += dashDrawButton(hx, hy, -1, "R1") + 4;
			hx = dashTextS(hx, hy + 4.5f, "10", DASH_FS_SMALL, DASH_C_TEXT2) + 12;
			dashModalHintRow(hx, hy, dashOkIcon(), "Apply", dashBackIcon(), "Cancel");
		}
		dashGfxPopOffset();
		dashGfxPopAlpha();
		dashGfxPresent();
	}
	if (accepted) { memcpy(fields, value, sizeof(value)); *settings = choice; }
	dashSoundPlay(accepted ? DASH_SND_CONFIRM : DASH_SND_CANCEL);
	dashInputFlush();
	return accepted;
}

static void setClockManually(void)
{
	char input[40], date[16], time[16], result[160];
	int fields[] = {2000, 1, 1, 0, 0, 0};
	int use12, datefmt;
	MenuClockSettings preferences;
	int ok;

	if (!dashWorkerAwaitAll("Finishing background storage work")) return;
	filerRootMcPollIdle();
	menuTitleLoadSavedClockSettings();
	if (!menuTitleGetClockFields(&fields[0], &fields[1], &fields[2], &fields[3], &fields[4], &fields[5],
	                             &use12, &datefmt)) {
		fields[0] = 2000;
		fields[1] = fields[2] = 1;
		fields[3] = fields[4] = fields[5] = 0;
	}
	menuTitleGetClockSettings(&preferences);
	if (!editClockDateTime(fields, &preferences))
		return;
	menuTitleFormatClockDate(date, sizeof(date), fields[0], fields[1], fields[2], preferences.date_format);
	menuTitleFormatClockTime(time, sizeof(time), fields[3], fields[4], fields[5], preferences.use_12h);
	snprintf(input, sizeof(input), "%s %s", date, time);
	if (!dashWorkerAwaitAll("Finishing background storage work")) return;
	filerRootMcPollIdle();
	ok = dashClockSetManualWithSettings(fields, &preferences, result, sizeof(result));
	dashModalMessage(ok ? DI_CHECK : DI_WARNING,
	                 ok ? "PS2 clock updated" : "Clock update failed", result, input);
}

#ifdef ETH
static void syncClockFromInternet(void)
{
	char result[160];
	int ok;

	if (!dashWorkerAwaitAll("Finishing background storage work"))
		return;
	dashLoadingBegin("Synchronizing PS2 clock");
	ok = dashClockSyncInternet(result, sizeof(result));
	dashLoadingEnd();
	dashModalMessage(ok ? DI_CHECK : DI_WARNING,
	                 ok ? "PS2 clock synchronized" : "Clock synchronization failed",
	                 result[0] ? result : (ok ? "The hardware clock was updated." : "No reliable Internet time was available."), NULL);
}
#endif

void dashSettingsSetPs2Clock(void)
{
	DashMenuItem items[] = {
	    {DI_CLOCK, "Set manually...", "Set local time, time zone, DST and hour format", 0},
#ifdef ETH
	    {DI_CLOCK, "Sync from Internet", "Use Internet time", 0},
#endif
	};
	int choice = dashModalMenu("Set PS2 Clock", NULL, items, NITEMS(items), 0);

	if (choice == 0)
		setClockManually();
#ifdef ETH
	else if (choice == 1)
		syncClockFromInternet();
#endif
}

