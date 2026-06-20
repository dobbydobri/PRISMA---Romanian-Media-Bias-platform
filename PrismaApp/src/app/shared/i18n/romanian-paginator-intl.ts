import { Injectable } from '@angular/core';
import { MatPaginatorIntl } from '@angular/material/paginator';


@Injectable()
export class RomanianPaginatorIntl extends MatPaginatorIntl {
  override itemsPerPageLabel = 'Articole pe pagină:';
  override nextPageLabel = 'Pagina următoare';
  override previousPageLabel = 'Pagina anterioară';
  override firstPageLabel = 'Prima pagină';
  override lastPageLabel = 'Ultima pagină';

  override getRangeLabel = (
    page: number,
    pageSize: number,
    length: number,
  ): string => {
    if (length === 0 || pageSize === 0) {
      return `0 din ${length}`;
    }
    const start = page * pageSize + 1;
    const end = Math.min((page + 1) * pageSize, length);
    return `${start} – ${end} din ${length}`;
  };
}
