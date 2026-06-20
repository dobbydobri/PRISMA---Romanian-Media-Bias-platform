import { Pipe, PipeTransform } from '@angular/core';
import {
  labelFor,
  TOPIC_LABELS,
  FRAMING_LABELS,
  OUTLET_TYPE_LABELS,
} from './labels';

const MAPS: Record<string, Record<string, string>> = {
  topic: TOPIC_LABELS,
  framing: FRAMING_LABELS,
  outletType: OUTLET_TYPE_LABELS,
};


@Pipe({ name: 'label', standalone: true })
export class LabelPipe implements PipeTransform {
  transform(
    value: string | null | undefined,
    type: 'topic' | 'framing' | 'outletType',
  ): string {
    return labelFor(MAPS[type], value);
  }
}
