"""수집 대상 영업일 목록. 이미 받은 날은 fetch 쪽에서 건너뛴다."""
import datetime as dt
import sys

start = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2025, 1, 1)
d, today = start, dt.date.today()
while d <= today:
    if d.weekday() < 5:
        print(d.strftime("%Y_%m_%d"))
    d += dt.timedelta(days=1)
