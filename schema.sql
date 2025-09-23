-- note that actually distinct field names need to be relatively unique for
-- natural join to work correctly
set role "speaker-to-postgres";

create language plpython3u;


drop function if exists current_client() cascade;
create function current_client() returns text as $$
    return GD.setdefault('mitsfs.client','SQL')
$$ language plpython3u;

drop function if exists set_client(text) cascade;
create function set_client(text) returns text as $$
    GD['mitsfs.client']=args[0]
    return GD['mitsfs.client']
$$ language plpython3u;


drop function if exists get_gd() cascade;
create function get_gd() returns text as $$
    import pprint
    return pprint.pformat(GD)
$$ language plpython3u;


drop function if exists update_row_modified() cascade;
create or replace function update_row_modified() returns trigger as $$
    if 'relname_plan' not in SD:
        SD['relname_plan'] = plpy.prepare('select relname from pg_class where oid=$1', ['oid'])
    relname_plan = SD['relname_plan']
    relid = TD['relid']
    relid_map = GD.setdefault('relid_map', {})
    if relid in relid_map:
        name = relid_map[relid]
    else:
        name = plpy.execute(relname_plan, [relid])[0]['relname']
        relid_map[relid] = name
    if 'user_plan' not in SD:
        SD['user_plan'] = plpy.prepare('select current_user')
    user_plan = SD['user_plan']
    current_user = plpy.execute(user_plan)[0]['current_user']
    for arg in ('_created', '_created_by', '_created_with'):
        if name + arg in TD['old']:
            TD['new'][name + arg] = TD['old'][name + arg]
    TD['new'][name + '_modified'] = 'now'
    TD['new'][name + '_modified_by'] = current_user
    TD['new'][name + '_modified_with'] = GD.setdefault('mitsfs.client','SQL')
    return 'MODIFY'
$$ language plpython3u;


drop function if exists insert_row_created_with() cascade;
create function insert_row_created_with() returns trigger as $$
    if 'relname_plan' not in SD:
        SD['relname_plan'] = plpy.prepare('select relname from pg_class where oid=$1', ['oid'])
    relname_plan = SD['relname_plan']
    relid = TD['relid']
    relid_map = GD.setdefault('relid_map', {})
    if relid in relid_map:
        name = relid_map[relid]
    else:
        name = plpy.execute(relname_plan, [relid])[0]['relname']
        relid_map[relid] = name
    TD['new'][name + '_created_with'] = GD.setdefault('mitsfs.client','SQL')
    TD['new'][name + '_modified_with'] = GD.setdefault('mitsfs.client','SQL')
    return 'MODIFY'
$$ language plpython3u;


drop function if exists collateral_update() cascade;
create function collateral_update() returns trigger as $$
    target = TD['args'][0]
    if target not in SD:
        SD[target] = plpy.prepare('update %s set %s_modified = current_timestamp where %s_id=$1' % (target, target, target), ['int4'])
    if TD['event'] != 'DELETE':
        row = TD['new']
    else:
        row = TD['old']
    plpy.execute(SD[target], [row[target+'_id']])
    return 'OK'
$$ language plpython3u;


drop function if exists log_row() cascade;
create function log_row() returns trigger as $$
    GD['TD'] = dict(TD)

    if 'relname_plan' not in SD:
        SD['relname_plan'] = plpy.prepare('select relname from pg_class where oid=$1', ['oid'])
    relname_plan = SD['relname_plan']
    relid = TD['relid']
    relid_map = GD.setdefault('relid_map', {})
    if relid in relid_map:
        name = relid_map[relid]
    else:
        name = plpy.execute(relname_plan, [relid])[0]['relname']
        relid_map[relid] = name

    event = TD['event']
    change = '%s %s\n' % (event, name)

    if TD['args'] is not None:
        id_column = TD['args'][0]
    else:
        id_column = name + '_id'
    filtercolumns = [name + i for i in ('_created',
                                        '_created_by',
                                        '_created_with',
                                        '_modified',
                                        '_modified_by',
                                        '_modified_with',)]

    if event == 'INSERT':
        log = [(column, str(value))
               for (column, value) in TD['new'].items()
               if column not in filtercolumns]
        obj_id = TD['new'][id_column]
    elif event == 'DELETE':
        log = [(column, str(value))
               for (column, value) in TD['old'].items()
               if column not in filtercolumns]
        obj_id = TD['old'][id_column]
    elif event == 'UPDATE':
        log = []
        for ((column, oldvalue), (othercolumn, newvalue)) in zip(TD['old'].items(), TD['new'].items()):
            if column not in filtercolumns and oldvalue != newvalue:
                log.append((column, str(oldvalue)))
                log.append((column, str(newvalue)))
        obj_id = TD['new'][id_column]

    for (column, value) in log:
        change += '%s %d\n' % (column, len(value.split('\n')))
        change += '%s\n' % value

    if 'log_plan' not in SD:
        SD['log_plan'] = plpy.prepare("INSERT INTO LOG (obj_id, relid, client, change) VALUES ($1,$2,$3,$4)", ['int4', 'oid', 'text', 'text'])
    log_plan = SD['log_plan']

    if log:
        plpy.execute(log_plan, [obj_id, relid, GD.setdefault('mitsfs.client','SQL'), change])
    return 'OK'
$$ language plpython3u;


create sequence id_seq;
grant select on id_seq to public;
grant update on id_seq to keyholders;


create table log (
       generation bigserial primary key,
       obj_id integer not null,
       stamp timestamp with time zone default current_timestamp not null,
       username varchar(64) default current_user not null,
       ip inet default inet_client_addr(),
       client text not null,
       relid oid not null,
       change text not null
);

create index log_id_relid_idx on log(obj_id, relid);

grant select, insert on log to keyholders;

select nextval('log_generation_seq');
-- so the pump is primed for exports

grant select, update on log_generation_seq to keyholders;


create table title (
       title_id integer default nextval('id_seq') not null primary key,
       title_lost boolean not null default false,
       title_created timestamp with time zone default current_timestamp not null,
       title_created_by varchar(64) default current_user not null,
       title_created_with varchar(64) default 'SQL' not null,
       title_modified timestamp with time zone default current_timestamp not null,
       title_modified_by varchar(64) default current_user not null,
       title_modified_with varchar(64) default 'SQL' not null
);

create trigger title_insert
       before insert on title for each row execute procedure insert_row_created_with();
create trigger title_update
       before update on title for each row execute procedure update_row_modified();
create trigger title_log
       before insert or update or delete on title for each row execute procedure log_row();

grant select on title to public;
grant insert, update, delete on title to panthercomm;


create table entity (
       entity_id integer default nextval('id_seq') not null primary key,
       -- aka integer references entity(entity_id),
       entity_name text unique not null,
       alternate_entity_name text,
       entity_created timestamp with time zone default current_timestamp not null,
       entity_created_by varchar(64) default current_user not null,
       entity_created_with varchar(64) default 'SQL' not null,
       entity_modified timestamp with time zone default current_timestamp not null,
       entity_modified_by varchar(64) default current_user not null,
       entity_modified_with varchar(64) default 'SQL' not null
       );

create index entity_name_idx on entity(entity_name);

create trigger entity_insert
       before insert on entity for each row execute procedure insert_row_created_with();
create trigger entity_update
       before update on entity for each row execute procedure update_row_modified();
create trigger entity_log
       before insert or update or delete on entity for each row execute procedure log_row();

grant select on entity to public;
grant insert, update, delete on entity to panthercomm;


create table title_responsibility_type (
       responsibility_type char(1) not null primary key,
       description text);

grant select on title_responsibility_type to public;
grant insert, update, delete on title_responsibility_type to libcomm;

insert into title_responsibility_type values ('?', 'Unspecified');
insert into title_responsibility_type values ('A', 'Author');
insert into title_responsibility_type values ('E', 'Editor');
insert into title_responsibility_type values ('P', 'Publisher');


create table title_responsibility (
       title_id integer not null references title,
       entity_id integer not null references entity,
       order_responsibility_by integer not null default 0,
       responsibility_type char(1) default 'A' not null references title_responsibility_type,
       unique (title_id, order_responsibility_by),
       check (responsibility_type != '=' or order_responsibility_by = 0));

create index title_responsibility_id_idx on title_responsibility(title_id);
create index title_responsibility_entity_id_idx on title_responsibility(entity_id);

create trigger title_responsibility_update
       before insert or update or delete on title_responsibility
       for each row execute procedure collateral_update('title');
create trigger title_responsibility_log
       before insert or update or delete on title_responsibility
       for each row execute procedure log_row('title_id');

grant select on title_responsibility to public;
grant insert, update, delete on title_responsibility to panthercomm;


create table title_title (
       title_id integer not null references title,
       title_name text not null,
       alternate_name text,
       order_title_by integer not null default 0,
       unique (title_id, order_title_by));

create trigger title_title_update
       before insert or update or delete on title_title
       for each row execute procedure collateral_update('title');
create trigger title_title_log
       before insert or update or delete on title_title
       for each row execute procedure log_row('title_id');

grant select on title_title to public;
grant insert, update, delete on title_title to panthercomm;


create table series (
       series_id integer default nextval('id_seq') not null primary key,
       series_name text not null,
       series_created timestamp with time zone default current_timestamp not null,
       series_created_by varchar(64) default current_user not null,
       series_created_with varchar(64) default 'SQL' not null,
       series_modified timestamp with time zone default current_timestamp not null,
       series_modified_by varchar(64) default current_user not null,
       series_modified_with varchar(64) default 'SQL' not null,
       unique(series_name));

create trigger series_insert
       before insert on series for each row execute procedure insert_row_created_with();
create trigger series_update
       before update on series for each row execute procedure update_row_modified();
create trigger series_log
       before insert or update or delete on series for each row execute procedure log_row();

grant select on series to public;
grant insert, update, delete on series to panthercomm;


create table title_series (
       title_id integer not null references title,
       series_id integer not null,
       series_index text,
       order_series_by integer not null default 0,
       series_visible boolean not null default false,
       number_visible boolean not null default false,
       unique (title_id, order_series_by));

create trigger title_series_update
       before insert or update or delete on title_series
       for each row execute procedure collateral_update('title');
create trigger title_series_log
       before insert or update or delete on title_series
       for each row execute procedure log_row('title_id');

grant select on title_series to public;
grant insert, update, delete on title_series to panthercomm;

create index title_series_series_idx on title_series(series_id);

create table format (
       format_id integer default nextval('id_seq') not null primary key,
       format text unique not null,
       format_description text not null,
       format_deprecated boolean default false not null);

grant select on format to public;
grant insert, update, delete on format to libcomm;

-- alter table format add column format_deprecated boolean default false not null;

--insert into format(format, format_description) values ('P', 'Paperback');
--insert into format(format, format_description) values ('H', 'Hardcover');
--insert into format(format, format_description) values ('LP', 'Large Paperback');
--insert into format(format, format_description) values ('VLP', 'Very Large Paperback');
--insert into format(format, format_description) values ('VLH', 'Very Large Hardcover');
insert into format(format, format_description) values ('?', 'Something');
insert into format(format, format_description) values ('S', 'Small (pocket paperback sized)');
insert into format(format, format_description) values ('L', 'Large (normal hardcover sized)');
insert into format(format, format_description) values ('VL', 'Very Large');
insert into format(format, format_description) values ('XL', 'Extra (Very Very Large)');


create table shelfcode_type (
    shelfcode_type char(1) unique primary key not null,
    shelfcode_type_description text not null);
grant select on shelfcode_type to public;
grant insert, update, delete on shelfcode_type to libcomm;

insert into shelfcode_type(shelfcode_type, shelfcode_type_description) values ('B', 'Boxed');
insert into shelfcode_type(shelfcode_type, shelfcode_type_description) values ('S', 'Special Reserve');
insert into shelfcode_type(shelfcode_type, shelfcode_type_description) values ('C', 'Circulating');
insert into shelfcode_type(shelfcode_type, shelfcode_type_description) values ('R', 'Reserve');
insert into shelfcode_type(shelfcode_type, shelfcode_type_description) values ('D', 'Deprecated');


create table shelfcode_class (
    shelfcode_class char(1) unique primary key not null,
    shelfcode_class_description text not null,
    shelfcode_class_hassle integer not null default 2);
grant select on shelfcode_class to public;
grant insert, update, delete on shelfcode_class to libcomm;

insert into shelfcode_class(shelfcode_class, shelfcode_class_description, shelfcode_class_hassle) values ('A', 'Anthology', 1);
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('C', 'Comics');
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('D', 'Double');
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('F', 'Fiction');
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('R', 'Reference');
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('T', 'Art');
insert into shelfcode_class(shelfcode_class, shelfcode_class_description) values ('?', '?');


create table shelfcode (
       shelfcode_id integer default nextval('id_seq') not null primary key,
       shelfcode text unique not null,
       shelfcode_description text not null,
       shelfcode_type char(1) default 'R' not null references shelfcode_type,
       replacement_cost numeric not null default 40,
       shelfcode_class char(1) default 'F' not null references shelfcode_class,
       shelfcode_doublecode boolean not null default false);

create index shelfcode_shelfcode_type on shelfcode(shelfcode_type);

grant select on shelfcode to public;
grant insert, update, delete on shelfcode to libcomm;

-- alter table shelfcode add column shelfcode_class char(1) default 'F' not null;


create table shelfcode_format (
       shelfcode_id integer,
       format_id integer);
grant select on shelfcode_format to public;
grant insert, update, delete on shelfcode_format to libcomm;


create table book (
       book_id integer default nextval('id_seq') not null primary key,
       title_id integer not null references title,
       shelfcode_id integer not null references shelfcode,
       book_series_visible boolean not null default false,
       doublecrap text,
       withdrawn boolean not null default false,
       review boolean not null default false,
       book_comment text,
       book_created timestamp with time zone default current_timestamp not null,
       book_created_by varchar(64) default current_user not null,
       book_created_with varchar(64) default 'SQL' not null,
       book_modified timestamp with time zone default current_timestamp not null,
       book_modified_by varchar(64) default current_user not null,
       book_modified_with varchar(64) default 'SQL' not null);

create index book_title_idx on book(title_id);
create index book_doublecrap_idx on book (doublecrap);
create index book_shelfcode_id_idx on book (shelfcode_id);
create unique index book_book_title_idx on book(book_id, title_id);

create trigger book_insert
       before insert on book for each row execute procedure insert_row_created_with();
create trigger book_update
       before update on book for each row execute procedure update_row_modified();
create trigger book_log
       before insert or update or delete on book for each row execute procedure log_row();

grant select on book to public;
grant insert, update, delete on book to panthercomm;


create table barcode (
       book_id integer not null references book,
       barcode text unique primary key not null,
       barcode_created timestamp with time zone default current_timestamp not null,
       barcode_created_by varchar(64) default current_user not null,
       barcode_created_with varchar(64) default 'SQL' not null,
       barcode_modified timestamp with time zone default current_timestamp not null,
       barcode_modified_by varchar(64) default current_user not null,
       barcode_modified_with varchar(64) default 'SQL' not null);

create index barcode_book_id_idx on barcode(book_id);

create trigger barcode_insert
       before insert on barcode
       for each row execute procedure insert_row_created_with();
create trigger barcode_update
       before update on barcode
       for each row execute procedure update_row_modified();
create trigger barcode_log
       before insert or update or delete on barcode
       for each row execute procedure log_row('book_id');

grant select on barcode to public;
grant insert on barcode to keyholders;
grant update, delete on barcode to panthercomm;

create or replace view shelf_count as
 select title_id, shelfcode, count(shelfcode) as bookcount
  from book natural join shelfcode
  where not withdrawn
  group by title_id, shelfcode;

grant select on shelf_count to public;

create view atdex as
 select title_id,
  array_to_string(array(select entity_name
                         from title_responsibility natural join entity
                         where title_responsibility.title_id = title.title_id
                         order by order_responsibility_by),'|') as author,
  array_to_string(array(select title_name
                          from title_title
                          where title_title.title_id = title.title_id
                          order by order_title_by),'|') as title
 from title
 order by author, title;


-- create view pinkdex as select
--   title_id, author, title,
--   array_to_string(array(select shelfcode
--                          from shelf_count
--                          where shelf_count.title_id = atdex.title_id and bookcount = 1
--                         union all
--                         select shelfcode||':'||bookcount
--                          from shelf_count
--                          where shelf_count.title_id = atdex.title_id and bookcount > 1
--                         order by shelfcode),',') as codes
--  from atdex
--  order by author, title;

create or replace view pinkdex as select * from
  (select title_id,
     array_agg(entity_name) as authors,
     array_agg(entity_id) as entity_ids,
     array_agg(responsibility_type) as responsibility_types,
     array_agg(order_responsibility_by) as order_responsibility_bys
   from title_responsibility natural join entity
   group by title_id) as authors
  natural join
  (select title_id,
   array_agg(concat_ws('=', title_name, alternate_name)) as titles,
   array_agg(order_title_by) as order_title_bys
   from title_title
   group by title_id) as titles
  natural join
  (select title_id,
   array_agg((case when book_series_visible then '@' else '' end) ||
             shelfcode || coalesce(doublecrap,'')) as shelfcodes,
   array_agg(shelfcode_id) as shelfcode_ids,
   array_agg(shelfcode_type) as shelfcode_types
   from book natural join shelfcode
   where not withdrawn
   group by title_id) as shelfcodes
  natural left join
  (select title_id,
     array_agg(series_name) as series,
     array_agg(series_index) as series_indexes,
     array_agg(series_visible) as series_visibles,
     array_agg(number_visible) as number_visibles,
     array_agg(series_id) as series_ids,
     array_agg(order_series_by) as order_series_bys
   from title_series natural join series
   group by title_id) as series;

grant select on pinkdex to public;

create table member (
       member_id integer default nextval('id_seq') not null primary key,
       pseudo boolean default false not null,
       rolname name,
       first_name text, 
       last_name text, 
       email text not null,
       phone text,
       address text,
       key_initials text,
 
       member_created timestamp with time zone default current_timestamp not null,
       member_created_by varchar(64) default current_user not null,
       member_created_with varchar(64) default current_client() not null,
       member_modified timestamp with time zone default current_timestamp not null,
       member_modified_by varchar(64) default current_user not null,
       member_modified_with varchar(64) default current_client() not null);

create trigger member_insert
       before insert on member for each row execute procedure insert_row_created_with();
create trigger member_update
       before update on member for each row execute procedure update_row_modified();
create trigger member_log
       before insert or update or delete on member for each row execute procedure log_row();

grant insert, update, select on member to keyholders;

insert into member(member_id, email, pseudo) select currval('id_seq'), 'CASH', true;

create table transaction (
       transaction_id integer default nextval('id_seq') not null primary key,
       transaction_amount numeric not null,
       member_id integer references member not null,
       transaction_type char not null,
       transaction_description text not null,

       transaction_created timestamp with time zone default current_timestamp not null,
       transaction_created_by varchar(64) default current_user not null,
       transaction_created_with varchar(64) default current_client());

create trigger transaction_log
       before update or delete on transaction for each row execute procedure log_row();
-- note no insert, log is implicit

create index transaction_member_id_idx on transaction(member_id);
create index transaction_transaction_created_idx on transaction(transaction_created);

grant insert, select on transaction to keyholders;


create table checkout (
       checkout_id integer default nextval('id_seq') not null primary key,
       member_id integer not null,
       checkout_stamp timestamp with time zone default current_timestamp,
       book_id integer references book,
       checkout_user text not null default current_user,
       checkin_user text default null,
       checkin_stamp timestamp with time zone default null,
       checkout_lost int references transaction,
       checkout_modified timestamp with time zone default null,
       checkout_modified_by varchar(64) default null,
       checkout_modified_with varchar(64) default null);

create index checkout_book_idx on checkout(book_id);
create index checkout_member_id on checkout(member_id);
grant insert, update, select on checkout to keyholders;

create trigger checkout_update
       before update on checkout for each row execute procedure update_row_modified();
create trigger checkout_log
       before insert or update or delete on checkout for each row execute procedure log_row();


-- create table checkout_member (
--        checkout_id integer not null references checkout,
--        member_id integer not null references member);
-- 
-- create unique index checkout_member_checkout_member_idx on checkout_member (checkout_id, member_id);
-- create unique index checkout_member_checkout_id_idx on checkout_member(checkout_id);
-- create index checkout_member_member_id_idx on checkout_member(member_id);
-- 
-- grant insert, update, select on checkout_member to keyholders;

create view top_checkout_titles as
 SELECT count(DISTINCT checkout.member_id) AS checkouts,
    book.title_id
   FROM checkout
	JOIN member USING (member_id)
    JOIN book USING (book_id)
    
  WHERE NOT member.pseudo
  GROUP BY book.title_id
  ORDER BY (count(DISTINCT checkout.member_id)) DESC;




create table inventory (
       inventory_id integer default nextval('id_seq') not null primary key,
       inventory_code text unique not null,
       inventory_stamp timestamp with time zone default current_timestamp not null,
       inventory_desc text not null,
       inventory_closed timestamp with time zone);

grant select on inventory to public;
grant insert, update, delete on inventory to libcomm;


create table shelf_divisions (
       title_id integer not null references title,
       inventory_id integer not null references inventory,
       shelfcode_id integer not null references shelfcode,
       division_comment text
);

grant select on shelf_divisions to public;
grant insert, update, delete on shelf_divisions to keyholders;


create table inventory_found (
       inventory_found_id integer default nextval('id_seq') not null primary key,
       inventory_id integer not null references inventory,
       title_id integer not null references title,
       format_id integer not null references format,
       found_tag text not null,
       inventory_reshelved boolean default false,
       orange boolean,
       flag boolean default false,
       inventory_entry_id integer,
       resolving_id integer);

grant select on inventory_found to public;
grant insert, update, delete on inventory_found to prentices;


create table inventory_packet (
       inventory_packet_id integer default nextval('id_seq') not null primary key,
       inventory_id integer not null references inventory,
       inventory_packet_name text not null);

grant select on inventory_packet to public;
grant insert, update, delete on inventory_packet to libcomm;


create table inventory_entry (
       inventory_entry_id integer default nextval('id_seq') not null primary key,
       inventory_id integer not null references inventory,
       title_id integer not null references title,
       shelfcode_id integer not null references shelfcode,
       inventory_packet_id integer references inventory_packet,
       entry_number integer,
       entry_expected integer not null default 0,
       book_series_visible boolean,
       doublecrap text,
       unique(inventory_id, title_id, shelfcode_id));

grant select on inventory_entry to public;
grant insert, update, delete on inventory_entry to libcomm;


create table inventory_missing (
       inventory_entry_id integer not null references inventory_entry,
       missing bool not null default true,
       missing_count integer);
grant select on inventory_missing to public;
grant insert, update, delete on inventory_entry to libcomm;


create table inventory_checkout (
       inventory_id integer not null references inventory,
       title_id integer not null references title,
       shelfcode_id integer not null references shelfcode,
       inventory_outcount integer not null);
grant select on inventory_missing to public;
grant insert, update, delete on inventory_entry to libcomm;


create table membership_type (
       membership_type_id integer default nextval('id_seq') not null,
       membership_type char(1) primary key,
       membership_type_cost numeric not null,
       membership_description text not null,
       membership_type_valid_from timestamp with time zone not null default '1969-07-21 02:56:15 +0',
       membership_type_valid_until timestamp with time zone,
       membership_duration interval,
       membership_type_active bool not null default 't',
       membership_type_created timestamp with time zone default current_timestamp not null,
       membership_type_created_by varchar(64) default current_user not null,
       membership_type_created_with varchar(64) default 'SQL' not null,
       membership_type_modified timestamp with time zone default current_timestamp not null,
       membership_type_modified_by varchar(64) default current_user not null,
       membership_type_modified_with varchar(64) default 'SQL' not null);

create trigger membership_type_insert
       before insert on membership_type for each row execute procedure insert_row_created_with();
create trigger membership_type_update
       before update on membership_type for each row execute procedure update_row_modified();
create trigger membership_type_log
       before insert or update or delete on membership_type for each row execute procedure log_row();

grant select on membership_type to keyholders;
grant insert, update, delete on membership_type to "*chamber";

insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_active) values ('P', 3000.0, 'Permanent', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_active) values ('L', 300.0, 'Life', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_active) values ('T', 5.0, '3 month', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_valid_until, membership_duration, membership_type_active) values ('Y', 10.0, 'old yearly', '2014-08-01 00:00 +0', '1 year', 'f');

insert into membership_type(membership_type, membership_type_cost, membership_description, membership_duration, membership_type_active) values ('1', 15.0, '1 year Nonstudent', '1 year', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_valid_until, membership_duration, membership_type_active) values ('2', 28.0, '2 year', '2014-08-15 03:00-04', '2 years', 'f');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_valid_until, membership_duration, membership_type_active) values ('3', 36.0, '3 year', '2014-08-15 03:00-04', '3 years', 'f');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_duration, membership_type_active) values ('4', 45.0, '4 year Nonstudent', '4 years', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_valid_from, membership_duration, membership_type_active) values ('!', 10.0, '1 year Student', '2014-08-15 03:00-04', '1 year', 't');
insert into membership_type(membership_type, membership_type_cost, membership_description, membership_type_valid_from, membership_duration, membership_type_active) values ('$', 20.0, '4 year Student', '2014-08-15 03:00-04', '4 years', 't');


--alter table membership_type add column membership_type_valid_from timestamp with time zone not null default '1969-07-21 02:56:15 +0';
--alter table membership_type add column membership_type_valid_until timestamp with time zone;
--alter table membership_type add column membership_duration interval;
--alter table membership_type add column membership_type_id integer default nextval('id_seq') not null;
--alter table membership_type add column membership_type_created timestamp with time zone default current_timestamp not null;
--alter table membership_type add column membership_type_created_by varchar(64) default current_user not null;
--alter table membership_type add column membership_type_created_with varchar(64) default 'SQL' not null;
--alter table membership_type add column membership_type_modified timestamp with time zone default current_timestamp not null;
--alter table membership_type add column membership_type_modified_by varchar(64) default current_user not null;
--alter table membership_type add column membership_type_modified_with varchar(64) default 'SQL' not null;

--update membership_type set membership_type_valid_until=current_timestamp where membership_type='S';
--update membership_type set membership_type_valid_until=current_timestamp where membership_type='Y';
--update membership_type set membership_duration='3 months' where membership_type='T';
--update membership_type set membership_description='3 month' where membership_type='T';

create table membership_cost (
       membership_cost_id integer default nextval('id_seq') not null primary key,
       membership_type char(1) references membership_type not null,
       membership_cost_valid_from timestamp with time zone not null default '1969-07-21 02:56:15 +0',
       membership_cost numeric not null,
       membership_cost_created timestamp with time zone default current_timestamp not null,
       membership_cost_created_by varchar(64) default current_user not null,
       membership_cost_created_with varchar(64) default 'SQL' not null,
       membership_cost_modified timestamp with time zone default current_timestamp not null,
       membership_cost_modified_by varchar(64) default current_user not null,
       membership_cost_modified_with varchar(64) default 'SQL' not null);

create trigger membership_cost_insert
       before insert on membership_cost for each row execute procedure insert_row_created_with();
create trigger membership_cost_update
       before update on membership_cost for each row execute procedure update_row_modified();
create trigger membership_cost_log
       before insert or update or delete on membership_cost for each row execute procedure log_row();

grant select on membership_cost to keyholders;
grant insert, update, delete on membership_cost to "*chamber";

create index membership_cost_type_valid_from_idx on membership_cost(membership_type, membership_cost_valid_from);

insert into membership_cost(membership_type, membership_cost) values ('P', 2600);
insert into membership_cost(membership_type, membership_cost) values ('L', 260);
insert into membership_cost(membership_type, membership_cost) values ('T', 5);
insert into membership_cost(membership_type, membership_cost) values ('1', 15);
insert into membership_cost(membership_type, membership_cost) values ('2', 28);
insert into membership_cost(membership_type, membership_cost) values ('3', 36);
insert into membership_cost(membership_type, membership_cost) values ('4', 44);
insert into membership_cost(membership_type, membership_cost) values ('!', 10);
insert into membership_cost(membership_type, membership_cost) values ('$', 20);
insert into membership_cost(membership_type, membership_cost, membership_cost_valid_from) values ('4', 45, '2014-08-15 03:00:00-04');
insert into membership_cost(membership_type, membership_cost, membership_cost_valid_from) values ('L', 300, '2014-08-15 03:00:00-04');
insert into membership_cost(membership_type, membership_cost, membership_cost_valid_from) values ('P', 3000, '2014-08-15 03:00:00-04');

-- create table fine (
--        fine_id integer default nextval('id_seq') primary key,
--        fine_name text not null,
--        fine numeric not null,
--        fine_valid_from timestamp with time zone not null default '1969-07-21 02:56:15 +0',
--        fine_created timestamp with time zone default current_timestamp not null,
--        fine_created_by varchar(64) default current_user not null,
--        fine_created_with varchar(64) default 'SQL' not null,
--        fine_modified timestamp with time zone default current_timestamp not null,
--        fine_modified_by varchar(64) default current_user not null,
--        fine_modified_with varchar(64) default 'SQL' not null);
-- 
-- create index fine_fine_name_idx on fine(fine_name);
-- create index fine_fine_name_valid_from on fine(fine_name, fine_valid_from);
-- 
-- create trigger fine_insert
--        before insert on fine for each row execute procedure insert_row_created_with();
-- create trigger fine_update
--        before update on fine for each row execute procedure update_row_modified();
-- create trigger fine_log
--        before insert or update or delete on fine for each row execute procedure log_row();

-- grant select on fine to keyholders;
-- grant insert, update, delete on fine to "*chamber";
-- 
-- insert into fine(fine_name, fine) values ('lateday', 0.25);
-- insert into fine(fine_name, fine) values ('maxlate', 10);
-- insert into fine(fine_name, fine, fine_valid_from) values ('lateday', 0.0, '2014-08-15 03:00-04');
-- insert into fine(fine_name, fine, fine_valid_from) values ('maxlate', 0, '2014-08-15 03:00-04');
-- insert into fine(fine_name, fine, fine_valid_from) values ('lateday', 0.10, '2014-09-06 03:00-04');
-- insert into fine(fine_name, fine, fine_valid_from) values ('maxlate', 4, '2014-09-06 03:00-04');

create table membership (
       membership_id integer default nextval('id_seq') primary key,
       member_id integer not null references member,
       membership_expires timestamp with time zone,
       membership_type char(1) references membership_type default 'Y' not null,
       membership_payment integer references transaction(transaction_id),

       membership_created timestamp with time zone default current_timestamp not null,
       membership_created_by varchar(64) default current_user not null,
       membership_created_with varchar(64) default current_client() not null,
       membership_modified timestamp with time zone default current_timestamp not null,
       membership_modified_by varchar(64) default current_user not null,
       membership_modified_with varchar(64) default current_client() not null);

create index membership_member_id on membership(member_id);

create trigger membership_insert
       before insert on membership for each row execute procedure insert_row_created_with();
create trigger membeship_update
       before update on membership for each row execute procedure update_row_modified();
create trigger membership_log
       before insert or update or delete on membership for each row execute procedure log_row();

grant insert, select on membership to keyholders;


create table fine_payment (
       checkout_id integer not null references checkout,
       transaction_id integer not null references transaction);

create trigger fine_payment_log
       before update or delete on fine_payment for each row execute procedure log_row();
-- note no insert

grant insert, select on fine_payment to keyholders;

create table transaction_link (
       transaction_id1 integer not null references transaction(transaction_id),
       transaction_id2 integer not null references transaction(transaction_id));

create trigger transaction_link_log
       before update or delete on transaction_link for each row execute procedure log_row();
-- note no insert

grant insert, select on transaction_link to keyholders;


create table timewarp (
       timewarp_id integer default nextval('id_seq') primary key,
       timewarp_start timestamp with time zone not null,
       timewarp_end timestamp with time zone not null,
       timewarp_modified timestamp with time zone default current_timestamp not null,
       timewarp_modified_by varchar(64) default current_user not null,
       timewarp_modified_with varchar(64) default 'SQL' not null,
       timewarp_created timestamp with time zone default current_timestamp not null,
       timewarp_created_by varchar(64) default current_user not null,
       timewarp_created_with varchar(64) default current_client());

create trigger timewarp_insert
       before insert on timewarp for each row execute procedure insert_row_created_with();
create trigger timewarp_update
       before update on timewarp for each row execute procedure update_row_modified();
create trigger timewarp_log
       before insert or update or delete on timewarp for each row execute procedure log_row();

grant select on timewarp to keyholders;
grant insert, update, delete on timewarp to "*chamber";

reset role;
