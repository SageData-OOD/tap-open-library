#!/usr/bin/env python3
import os
import json
import singer
from singer import utils, metadata
from singer.catalog import Catalog, CatalogEntry
from singer.schema import Schema
from .tap_open_library import get_recent_changes
from singer.transform import transform


REQUIRED_CONFIG_KEYS = ["change_date", "kind"]
LOGGER = singer.get_logger()


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


def load_schemas():
    """ Load schemas from schemas folder """
    schemas = {}
    for filename in os.listdir(get_abs_path("schemas")):
        path = get_abs_path("schemas") + "/" + filename
        file_raw = filename.replace(".json", "")
        with open(path) as file:
            schemas[file_raw] = Schema.from_dict(json.load(file))
    return schemas


def discover():
    raw_schemas = load_schemas()
    streams = []
    for stream_id, schema in raw_schemas.items():
        # TODO: populate any metadata and stream's key properties here..
        stream_metadata = []
        key_properties = ["id"]
        streams.append(
            CatalogEntry(
                tap_stream_id=stream_id,
                stream=stream_id,
                schema=schema,
                key_properties=key_properties,
                metadata=metadata.get_standard_metadata(schema.to_dict(), stream_id),
                replication_key=None,
                is_view=None,
                database=None,
                table=None,
                row_count=None,
                stream_alias=None,
                replication_method=None,
            )
        )
    return Catalog(streams)


def sync(config, state, catalog):
    """ Sync data from tap source """
    # Loop over selected streams in catalog
    for stream in catalog.get_selected_streams(state):
        LOGGER.info("Syncing stream:" + stream.tap_stream_id)
        mdata = metadata.to_map(stream.metadata)
        bookmark_column = stream.replication_key

        is_sorted = False
        schema = stream.schema.to_dict()
        singer.write_schema(
            stream_name=stream.tap_stream_id,
            schema=schema,
            key_properties=stream.key_properties,
        )

        tap_data = get_recent_changes(config=config)

        max_bookmark = None
        for row in tap_data:
            transformed_data = transform(row, schema, metadata=mdata)
            # write one or more rows to the stream:
            singer.write_records(stream.tap_stream_id, [transformed_data])
            if bookmark_column:
                if is_sorted:
                    # update bookmark to latest value
                    singer.write_state({stream.tap_stream_id: transformed_data[bookmark_column]})
                else:
                    # if data unsorted, save max value until end of writes
                    max_bookmark = max(max_bookmark, transformed_data[bookmark_column])
        if bookmark_column and not is_sorted:
            singer.write_state({stream.tap_stream_id: max_bookmark})
    return


@utils.handle_top_exception(LOGGER)
def main():
    # Parse command line arguments
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)

    # If discover flag was passed, run discovery mode and dump output to stdout
    if args.discover:
        catalog = discover()
        catalog.dump()
    # Otherwise run in sync mode
    else:
        if args.catalog:
            catalog = args.catalog
        else:
            catalog = discover()

        sync(args.config, args.state, catalog)


if __name__ == "__main__":
    main()
