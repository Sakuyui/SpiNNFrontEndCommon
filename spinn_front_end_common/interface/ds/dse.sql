-- Copyright (c) 2018 The University of Manchester
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.


-- This file should be a clone of
-- JavaSpiNNaker/SpiNNaker-storage/src/main/resources/dse.sql

-- https://www.sqlite.org/pragma.html#pragma_synchronous
PRAGMA main.synchronous = OFF;
PRAGMA foreign_keys = ON;

-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- A table describing the ethernets.
CREATE TABLE IF NOT EXISTS ethernet(
    ethernet_x INTEGER NOT NULL,
    ethernet_y INTEGER NOT NULL,
    ip_address TEXT UNIQUE NOT NULL,
    PRIMARY KEY (ethernet_x, ethernet_y));

-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- A table describing the chips and their ethernet.
CREATE TABlE IF NOT EXISTS chip(
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    ethernet_x INTEGER NOT NULL,
    ethernet_y INTEGER NOT NULL,
    PRIMARY KEY (x, y),
    FOREIGN KEY (ethernet_x, ethernet_y)
        REFERENCES ethernet(ethernet_x, ethernet_y)
    );

CREATE VIEW IF NOT EXISTS chip_view AS
    SELECT x, y, ethernet_x, ethernet_y, ip_address
    FROM ethernet NATURAL JOIN chip;

-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- A table describing the cores.
CREATE TABLE IF NOT EXISTS core(
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    p INTEGER NOT NULL,
    is_system INTEGER NOT NULL,
    base_address INTEGER,
    PRIMARY KEY (x, y, p),
    FOREIGN KEY (x, y) REFERENCES chip(x, y)
);

CREATE VIEW IF NOT EXISTS core_view AS
    SELECT x, y, p, base_address, is_system,
           ethernet_x, ethernet_y, ip_address
    FROM core NATURAL JOIN chip_view;

-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- A table describing the regions.
CREATE TABLE IF NOT EXISTS region(
    region_num INTEGER NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    p INTEGER NOT NULL,
    reference_num INTEGER,
    content BLOB,
    content_debug TEXT,
    size INT NOT NULL,
    pointer INTEGER,
    region_label TEXT,
    PRIMARY KEY (x, y, p, region_num),
    FOREIGN KEY (x, y, p) REFERENCES core(x, y, p));

CREATE VIEW IF NOT EXISTS region_view AS
    SELECT x, y, p, base_address, is_system,
           region_num, region_label, reference_num, content, content_debug,
           length(content) as content_size, size, pointer
    FROM chip NATURAL JOIN core NATURAL JOIN region;

-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- A table describing the references.
CREATE TABLE IF NOT EXISTS reference (
    reference_num INTEGER NOT NULL,
    region_num INTEGER NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    p INTEGER NOT NULL,
    ref_label TEXT,
    PRIMARY KEY (x, y, p, region_num),
    FOREIGN KEY (x, y, p) REFERENCES core(x, y, p));

-- -- Every reference os unique per core
CREATE UNIQUE INDEX IF NOT EXISTS reference_sanity ON reference(
    x ASC, Y ASC, p ASC, reference_num ASC);

CREATE VIEW IF NOT EXISTS reverence_view AS
SELECT x, y, p, region_num, reference_num, ref_label
FROM reference NATURAL JOIN core NATURAL JOIN chip;

CREATE VIEW IF NOT EXISTS linked_reverence_view AS
SELECT reverence_view.reference_num, reverence_view.x as x, reverence_view.y as y,
       reverence_view.p as ref_p, reverence_view.region_num as ref_region, ref_label,
       region_view.p as act_p, region_view.region_num as act_region, region_label,
       region_view.size,  pointer
FROM reverence_view LEFT JOIN region_view
ON reverence_view.reference_num = region_view.reference_num
    AND reverence_view.x = region_view.x
    AND reverence_view.y = region_view.y;

CREATE TABLE IF NOT EXISTS app_id (
    app_id INTEGER NOT NULL
);

-- Information about how to access the connection proxying
-- WARNING! May include credentials
CREATE TABLE IF NOT EXISTS proxy_configuration(
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL);
