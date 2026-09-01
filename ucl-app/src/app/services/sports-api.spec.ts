import { TestBed } from '@angular/core/testing';

import { SportsApi } from './sports-api';

describe('SportsApi', () => {
  let service: SportsApi;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(SportsApi);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
