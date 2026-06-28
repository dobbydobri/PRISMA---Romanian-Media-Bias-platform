import { Pipe, PipeTransform } from '@angular/core';

const RO_MONTHS = [
  'ian', 'feb', 'mar', 'apr', 'mai', 'iun',
  'iul', 'aug', 'sep', 'oct', 'nov', 'dec',
];

/**
 * Formats an ISO datetime string into Romanian short-date format: "27 iun 2025".
 * Pure pipe — no re-execution unless the input reference changes.
 */
@Pipe({
  name: 'roDate',
  standalone: true,
  pure: true,
})
export class RoDatePipe implements PipeTransform {
  transform(value: string | null | undefined): string | null {
    if (!value) return null;
    const d = new Date(value);
    if (isNaN(d.getTime())) return null;
    return `${d.getDate()} ${RO_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  }
}
