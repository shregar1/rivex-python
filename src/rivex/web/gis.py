from __future__ import annotations

import math
from typing import Any


class Geometry:
    """Base geometry class using WKT representation."""

    wkt_type: str = "GEOMETRY"

    def __init__(self, coordinates: Any, srid: int = 4326):
        self.coordinates = coordinates
        self.srid = srid

    def __str__(self) -> str:
        return self.wkt()

    def wkt(self) -> str:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.wkt_type} SRID={self.srid}>"


class Point(Geometry):
    wkt_type = "POINT"

    def __init__(self, x: float, y: float, srid: int = 4326, z: float | None = None):
        super().__init__((x, y, z) if z is not None else (x, y), srid)
        self.x = x
        self.y = y
        self.z = z

    def wkt(self) -> str:
        coord_str = f"{self.x} {self.y}"
        if self.z is not None:
            coord_str += f" {self.z}"
        return f"{self.wkt_type}({coord_str})"

    def __repr__(self) -> str:
        return f"<Point({self.x}, {self.y}) SRID={self.srid}>"


class LineString(Geometry):
    wkt_type = "LINESTRING"

    def __init__(self, points: list[tuple[float, float]], srid: int = 4326):
        super().__init__(points, srid)

    def wkt(self) -> str:
        coords = ", ".join(f"{x} {y}" for x, y in self.coordinates)
        return f"{self.wkt_type}({coords})"


class Polygon(Geometry):
    wkt_type = "POLYGON"

    def __init__(self, rings: list[list[tuple[float, float]]], srid: int = 4326):
        super().__init__(rings, srid)

    def wkt(self) -> str:
        rings_str = ", ".join(
            "(" + ", ".join(f"{x} {y}" for x, y in ring) + ")"
            for ring in self.coordinates
        )
        return f"{self.wkt_type}({rings_str})"


class MultiPoint(Geometry):
    wkt_type = "MULTIPOINT"

    def __init__(self, points: list[tuple[float, float]], srid: int = 4326):
        super().__init__(points, srid)

    def wkt(self) -> str:
        coords = ", ".join(f"{x} {y}" for x, y in self.coordinates)
        return f"{self.wkt_type}({coords})"


class MultiLineString(Geometry):
    wkt_type = "MULTILINESTRING"

    def __init__(self, lines: list[list[tuple[float, float]]], srid: int = 4326):
        super().__init__(lines, srid)

    def wkt(self) -> str:
        lines_str = ", ".join(
            "(" + ", ".join(f"{x} {y}" for x, y in line) + ")"
            for line in self.coordinates
        )
        return f"{self.wkt_type}({lines_str})"


class MultiPolygon(Geometry):
    wkt_type = "MULTIPOLYGON"

    def __init__(self, polygons: list[list[list[tuple[float, float]]]], srid: int = 4326):
        super().__init__(polygons, srid)

    def wkt(self) -> str:
        polys_str = ", ".join(
            "(" + ", ".join(
                "(" + ", ".join(f"{x} {y}" for x, y in ring) + ")"
                for ring in polygon
            ) + ")"
            for polygon in self.coordinates
        )
        return f"{self.wkt_type}({polys_str})"


class GeometryCollection(Geometry):
    wkt_type = "GEOMETRYCOLLECTION"

    def __init__(self, geometries: list[Geometry], srid: int = 4326):
        super().__init__(geometries, srid)

    def wkt(self) -> str:
        geoms = ", ".join(g.wkt() for g in self.coordinates)
        return f"{self.wkt_type}({geoms})"


class GeographyColumn:
    """Descriptor for a geography column on a model."""

    def __init__(self, geometry_type: str = "POINT", srid: int = 4326):
        self.geometry_type = geometry_type
        self.srid = srid

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.get(self.name)

    def __set__(self, instance, value):
        if isinstance(value, (list, tuple)):
            value = Point(*value, srid=self.srid)
        instance.__dict__[self.name] = value


GeometryColumn = GeographyColumn


class SpatialQuery:
    """Builder for spatial SQL queries."""

    def __init__(self, column: str):
        self._column = column

    def distance(self, point: Point) -> str:
        return f"ST_Distance({self._column}, ST_GeomFromText('{point.wkt()}', {point.srid}))"

    def within(self, polygon: Polygon) -> str:
        return f"ST_Within({self._column}, ST_GeomFromText('{polygon.wkt()}', {polygon.srid}))"

    def intersects(self, geometry: Geometry) -> str:
        return f"ST_Intersects({self._column}, ST_GeomFromText('{geometry.wkt()}', {geometry.srid}))"

    def contains(self, geometry: Geometry) -> str:
        return f"ST_Contains({self._column}, ST_GeomFromText('{geometry.wkt()}', {geometry.srid}))"

    def bbox(self, min_x: float, min_y: float, max_x: float, max_y: float) -> str:
        return (f"{self._column} && ST_MakeEnvelope({min_x}, {min_y}, {max_x}, {max_y}, 4326)")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in kilometers between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def earth_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_distance(lat1, lon1, lat2, lon2)


def to_geojson(geometry: Geometry) -> dict:
    """Convert a Rivex geometry to a GeoJSON dictionary."""
    type_map = {
        "POINT": "Point",
        "LINESTRING": "LineString",
        "POLYGON": "Polygon",
        "MULTIPOINT": "MultiPoint",
        "MULTILINESTRING": "MultiLineString",
        "MULTIPOLYGON": "MultiPolygon",
        "GEOMETRYCOLLECTION": "GeometryCollection",
    }
    result: dict = {
        "type": type_map.get(geometry.wkt_type, "Point"),
        "coordinates": geometry.coordinates,
    }
    result["crs"] = {"type": "name", "properties": {"name": f"EPSG:{geometry.srid}"}}
    return result
