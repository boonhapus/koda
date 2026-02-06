import marimo

__generated_with = "0.19.7"
app = marimo.App(width="columns", sql_output="polars")


@app.cell(column=0)
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    from typing import Annotated, Any, Literal
    import asyncio
    import pathlib
    import os

    from koda._task import InstrumentedCoroutine, InstrumentedTask
    from koda import __project__
    return Annotated, Any, Literal, __project__, asyncio, os, pathlib


@app.cell
def _(OpenDotaAPI, StratzAPI, os, pathlib):
    db_cache_path = pathlib.Path("./nb/cache.db")

    opendota = OpenDotaAPI(cache_path=db_cache_path)
    stratz   = StratzAPI(token=os.environ["STRATZ_TOKEN"], cache_path=db_cache_path)
    return (stratz,)


@app.cell
async def _(Match, stratz):
    _r = await stratz.match(match_id=8678575691)
    _m = Match.model_validate(_r.json(), context={"provider": "STRATZ"})
    _m.players
    return


@app.cell
def _(mo):
    mo.md(rf"""
    # Infographic

    Can we create an infographic for this data, at a given time?

    {mo.image(src="nb/public/minimap.png")}
    {mo.image(src="nb/public/hero-item-stats.png")}
    """)
    return


@app.cell(column=1)
def _():
    import datetime as dt
    import hashlib
    import json

    import aiosqlite
    import glom
    import niquests
    import pydantic
    return aiosqlite, dt, glom, hashlib, json, niquests, pydantic


@app.cell
def _(Annotated, Any, Literal, ValidationInfo, dt, glom, pydantic):
    class GlomModel(pydantic.BaseModel):
        """A base class which defers to Glom under specific context."""

        @pydantic.model_validator(mode="before")
        @classmethod
        def defer_to_glom(cls, data: Any, info: ValidationInfo) -> Any:
            if info.context is None:
                return data

            if info.context["provider"] == "STRATZ":
                return cls.__stratz_api__(data)

            return data


    class UnitMovement(GlomModel):
        """Represents the data about the location of a unit in a match."""
        timestamp: int
        x: int
        y: int

        @classmethod
        def __stratz_api__(cls, data: dict[str, Any]) -> dict[str, Any]:
            """Reshapes a STRATZ response into a MatchPlayer schema."""

            spec = {
                "timestamp": "time",
                "x": "x",
                "y": "y",
            }

            return glom.glom(data, spec)


    class MatchPlayer(GlomModel):
        """Represents the data about a DOTA player in a match."""
        steam_account_id: int
        party_id: int | None
        player_slot: int
        team: Literal["RADIANT", "DIRE"]
        hero_id: int
        is_random: bool
        leaver_status: str | None
        award: Literal["MVP", "TOP_CORE", "TOP_SUPPORT"] | None
        prediction_streak: int | None
        position: int | None
        role: Literal["CORE", "LIGHT_SUPPORT", "HARD_SUPPORT"] | None
        movement: list[UnitMovement]

        @pydantic.field_validator("team", mode="before")
        @classmethod
        def bool_to_enum(cls, value: bool | str) -> Literal["RADIANT", "DIRE"]:
            if isinstance(value, str):
                return value
            return "RADIANT" if value else "DIRE"

        @pydantic.field_validator("leaver_status", "award", mode="before")
        @classmethod
        def coerce_none(cls, value: str | None) -> str | None:
            if value == "NONE":
                return None
            return value

        @pydantic.field_validator("position", mode="before")
        @classmethod
        def coerce_position(cls, value: str | int | None) -> int | None:
            if value is None or isinstance(value, int):
                return value
            return int(value.replace("POSITION_", ""))

        @classmethod
        def __stratz_api__(cls, data: dict[str, Any]) -> dict[str, Any]:
            """Reshapes a STRATZ response into a MatchPlayer schema."""
            spec = {
                "steam_account_id": "steamAccountId",
                "party_id": "partyId",
                "player_slot": "playerSlot",
                "team": "isRadiant",
                "hero_id": "heroId",
                "is_random": "isRandom",
                "leaver_status": "leaverStatus",
                "award": "award",
                "position": "position",
                "prediction_streak": "streakPrediction",
                "role": "role",
                "movement": "playbackData.playerUpdatePositionEvents",
            }

            return glom.glom(data, spec)


    class Match(GlomModel):
        """Represents the data about a DOTA match."""
        match_id: int
        league_id: int | None
        series_id: int | None
        region_id: int
        game_version_id: int
        start_dt: Annotated[pydantic.AwareDatetime, "in UTC"]
        duration: int
        game_mode: str
        is_ranked: bool
        rank: int
        radiant_win: bool
        players: list[MatchPlayer]

        @pydantic.field_validator("start_dt", mode="before")
        @classmethod
        def timestamp_to_utc_dt(cls, value: int | dt.datetime) -> dt.datetime:
            if isinstance(value, dt.datetime):
                return value
            return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)

        @classmethod
        def __stratz_api__(cls, data: dict[str, Any]) -> dict[str, Any]:
            """Reshapes a STRATZ response into a Match schema."""

            spec = {
                "match_id": "data.match.id",
                "league_id": "data.match.leagueId",
                "series_id": "data.match.seriesId",
                "region_id": "data.match.regionId",
                "game_version_id": "data.match.gameVersionId",
                "start_dt": "data.match.startDateTime",
                "duration": "data.match.durationSeconds",
                "game_mode": "data.match.gameMode",
                "is_ranked": "data.match.isStats",
                "rank": "data.match.actualRank",
                "radiant_win": "data.match.didRadiantWin",
                "players": "data.match.players",
            }

            return glom.glom(data, spec)
    return (Match,)


@app.cell(column=2)
def _(AsyncRateLimitHook, SQLiteCacheMixin, __project__, niquests):
    class StratzAPI(SQLiteCacheMixin, niquests.AsyncSession):
        """
        Interfaces with the STRATZ API.

        Further reading:
          - https://stratz.com/api
        """
        ONE_DAY_IN_SECONDS = 60 * 24

        def __init__(self, token: str, **options) -> None:
            RETRY_POLICY = niquests.RetryConfiguration(
                total=5,
                backoff_factor=2,
                status_forcelist=[429, 500, 503],
                allowed_methods=["GET", "POST"],
                raise_on_status=False,
                respect_retry_after_header=True,
            )
            super().__init__(
                base_url="https://api.stratz.com",
                headers={
                    "User-Agent": f"STRATZ_API [Koda v{__project__.__version__} (github: @boonhapus/koda)]",
                    "Authorization": f"Bearer {token}",
                },
                hooks=AsyncRateLimitHook(rps=10_000 / StratzAPI.ONE_DAY_IN_SECONDS),
                retries=RETRY_POLICY,
                cache_ttl=StratzAPI.ONE_DAY_IN_SECONDS,
                **options,
            )

        async def query(self, query: str, **variables) -> niquests.Response:
            """
            Issue a GraphQL query.

            Further reading:
              - https://api.stratz.com/graphiql
            """
            u = "/graphql"
            d = {"query": query, "variables": variables}
            r = await self.post(u, json=d)
            return r

        async def match(self, match_id: int) -> niquests.Response:
            """Match data."""
            q = """
            query GetMatch($id: Long!) {
              match(id: $id) {
                id
                leagueId
                seriesId
                regionId
                gameVersionId
                startDateTime
                durationSeconds
                gameMode
                isStats  # lobbyType?
                actualRank
                didRadiantWin

                players {
                  steamAccountId
                  partyId
                  playerSlot
                  isRadiant
                  heroId
                  isRandom
                  leaverStatus
                  award
                  position
                  streakPrediction
                  role

                  playbackData {
                    playerUpdatePositionEvents {
                      time
                      x
                      y
                    }
                  }
                }
              }
            }
            """
            r = await self.query(q, id=match_id)
            return r
    return (StratzAPI,)


@app.cell(column=3)
def _(AsyncRateLimitHook, SQLiteCacheMixin, __project__, niquests):
    class OpenDotaAPI(SQLiteCacheMixin, niquests.AsyncSession):
        """
        Interfaces with the OpenDotA API.

        Further reading:
          - https://docs.opendota.com/#section/Introduction
          - https://www.opendota.com/api-keys
        """
        ONE_DAY_IN_SECONDS = 60 * 24

        def __init__(self, **options) -> None:
            RETRY_POLICY = niquests.RetryConfiguration(
                total=5,
                backoff_factor=2,
                status_forcelist=[429, 500, 503, 521, 522],
                allowed_methods=["GET"],
                raise_on_status=False,
                respect_retry_after_header=True,
            )
            super().__init__(
                base_url="https://api.opendota.com/api",
                headers={"User-Agent": f"Koda v{__project__.__version__} (github: @boonhapus/koda)"},
                hooks=AsyncRateLimitHook(rps=3_000 / OpenDotaAPI.ONE_DAY_IN_SECONDS),
                retries=RETRY_POLICY,
                cache_ttl=OpenDotaAPI.ONE_DAY_IN_SECONDS,
                **options,
            )

        async def explorer(self, sql: str) -> niquests.Response:
            """
            Submit arbitrary SQL queries to the database.

            Further reading:
              - https://docs.opendota.com/#tag/explorer/operation/get_explorer
            """
            u = "/explorer"
            p = {"sql": sql}
            r = await self.get(u, params=p)
            return r

        async def match(self, match_id: int) -> niquests.Response:
            """
            Match data.

            Further reading:
              - https://docs.opendota.com/#tag/matches/operation/get_matches_by_match_id
            """
            u = f"/matches/{match_id}"
            r = await self.get(u)
            return r
    return (OpenDotaAPI,)


@app.cell(column=4)
def _(asyncio, niquests):
    class AsyncRateLimitHook(niquests.AsyncLifeCycleHook):
        """A simple async rate limiter."""

        def __init__(self, rps: float = 1.0):
            self.delay = 1.0 / rps
            self.last_call = 0.0
            self.lock = asyncio.Lock()
            super().__init__()

        async def pre_request(self, request: niquests.Request, **kwargs) -> niquests.Request:
            """
            The prepared request just got built.

            You may alter it prior to be sent through HTTP.
            """
            async with self.lock:
                elapsed = asyncio.get_event_loop().time() - self.last_call

                if wait := max(0, self.delay - elapsed):
                    await asyncio.sleep(wait)

                self.last_call = asyncio.get_event_loop().time()

            return request
    return (AsyncRateLimitHook,)


@app.cell
def _(Response, aiosqlite, dt, hashlib, json, niquests):
    class SQLiteCacheMixin:
        """Mixin that allows for caching requests."""
        def __init__(self, cache_path: str = "cache.db", cache_ttl: int = 3600, **kwargs):
            super().__init__(**kwargs)
            self.path = cache_path
            self.ttl = cache_ttl
            self._db: aiosqlite.Connection | None = None

        async def _get_db(self) -> aiosqlite.Connection:
            if self._db is not None:
                return self._db

            self._db = await aiosqlite.connect(self.path)
            self._db.row_factory = aiosqlite.Row

            await self._db.executescript("""
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY, 
                    url TEXT, 
                    status INTEGER, 
                    headers TEXT, 
                    content BLOB, 
                    expires DATETIME
                );
                CREATE INDEX IF NOT EXISTS idx_exp ON cache(expires);
            """)

            return self._db

        def _make_key(self, method: str, url: str, **kwargs) -> str:
            parts = [method.upper(), url]

            if d := kwargs.get("data"):
                parts.append(json.dumps(d, sort_keys=True))

            if j := kwargs.get("json"):
                parts.append(json.dumps(j, sort_keys=True))

            if p := kwargs.get("params"):
                parts.append(json.dumps(p, sort_keys=True))

            return hashlib.sha256("::".join(parts).encode()).hexdigest()

        async def request(
            self,
            method: str,
            url: str,
            should_cache: bool = True,
            bust_cache: bool = False,
            **kwargs,
        ) -> Response:
            """Override the default request logic to implement caching."""
            db = await self._get_db()

            # 1. CHECK IF CACHED
            if should_cache and not bust_cache:
                q = "SELECT * FROM cache WHERE key = ? AND expires > ?"
                k = self._make_key(method.upper(), url, **kwargs)
                e = dt.datetime.now(tz=dt.timezone.utc)

                async with db.execute(q, (k, e)) as cursor:
                    if (row := await cursor.fetchone()):
                        # FAKE IT FROM THE CACHE
                        r = niquests.Response()
                        r.url = row["url"]
                        r.status_code = row["status"]
                        r.headers.update(json.loads(row["headers"]))
                        r._content = row["content"]
                        r._content_consumed = True
                        return r

            # 2. EXECUTE NETWORK REQUEST
            r = await super().request(method, url, **kwargs)

            # 3. CACHE IF SUCCESSFUL
            if should_cache and r.status_code < 300:
                q = "INSERT OR REPLACE INTO cache (key, url, status, headers, content, expires) VALUES (?, ?, ?, ?, ?, ?)"
                k = self._make_key(method.upper(), url, **kwargs)
                u = str(r.url)
                s = r.status_code
                h = json.dumps(dict(r.headers))
                c = r.content
                e = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=self.ttl)

                await db.execute(q, (k, u, s, h, c, e))
                await db.commit()

            return r

        async def close(self) -> None:
            """Ensure the aiosqlite connection is closed when the session closes."""
            if self._db is not None:
                await self._db.close()
            await super().close()
    return (SQLiteCacheMixin,)


if __name__ == "__main__":
    app.run()
