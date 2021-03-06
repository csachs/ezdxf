# Purpose: entity space
# Created: 13.03.2011
# Copyright (C) 2011, Manfred Moitzi
# License: MIT License

from __future__ import unicode_literals
__author__ = "mozman <mozman@gmx.at>"

from .lldxf.const import DXFStructureError


class EntitySpace(list):
    """
    An EntitySpace is a collection of drawing entities.
    The ENTITY section is such an entity space, but also blocks.
    The EntitySpace stores only handles to the drawing entity database.
    """
    def __init__(self, entitydb):
        self._entitydb = entitydb

    def get_tags_by_handle(self, handle):
        return self._entitydb[handle]

    def store_tags(self, tags):
        handle = tags.get_handle()
        self.append(handle)
        return handle

    def write(self, tagwriter):
        for handle in self:
            # write linked entities
            while handle is not None:
                tags = self._entitydb[handle]
                tagwriter.write_tags(tags)
                handle = tags.link

    def delete_entity(self, entity):
        # do not delete database objects - entity space just manage handles
        self.remove(entity.dxf.handle)

    def delete_all_entities(self):
        # do not delete database objects - entity space just manage handles
        del self[:]

    def add_handle(self, handle):
        self.append(handle)


class LayoutSpaces(object):
    def __init__(self, entitydb, dxfversion):
        self._layout_spaces = {}
        self._entitydb = entitydb
        self._dxfversion = dxfversion
        if dxfversion <= 'AC1009':
            self._get_key = lambda t: t.noclass.get_first_value(67, default=0)  # paper space value
        else:
            self._get_key = lambda t: t.noclass.get_first_value(330, default=0)  # if no owner tag, set 0 and repair later

    def __iter__(self):
        """ Iterate over all layout entity spaces.
        """
        return iter(self._layout_spaces.values())

    def __getitem__(self, key):
        """ Get layout entity space by *key*.
        """
        return self._layout_spaces[key]

    def __len__(self):
        return sum(len(entity_space) for entity_space in self._layout_spaces.values())

    def handles(self):
        """ Iterate over all handles in all entity spaces.
        """
        for entity_space in self:
            for handle in entity_space:
                yield handle

    def repair_owner_tags(self, model_space_key, paper_space_key):
        def update_entity_tags(entity_space):
            for handle in entity_space:
                tags = entity_space.get_tags_by_handle(handle)
                try:
                    entity_tags = tags.get_subclass("AcDbEntity")
                except KeyError:
                    raise DXFStructureError("Entity has no subclass 'AcDbEntity'.")

                if entity_tags.get_first_value(67, default=0) == 0:  # 67 = paper_space tag (fixed)
                    key = model_space_key  # paper_space tag is 0 -> model space
                else:
                    key = paper_space_key  # paper_space tag is not 0 -> paper space

                tags.noclass.set_first(330, key)

        def distribute(entity_space):
            for handle in entity_space:
                tags = entity_space.get_tags_by_handle(handle)
                owner = tags.noclass.get_first_value(330)
                if owner == model_space_key:
                    model_space.add_handle(handle)
                elif owner == paper_space_key:
                    paper_space.add_handle(handle)
                else:
                    raise DXFStructureError("Invalid owner handle {}".format(handle))

        if self._dxfversion <= 'AC1009':
            return
        if 0 not in self._layout_spaces:  # no temporary model space exists
            return

        # All entities of model space and the active paper space are stored in the ENTITIES section.
        # If (the not mandatory) owner tag is not present, the owner tag is temporarily set to '0'.
        # The (not mandatory) paper_space tag decides where the entity goes: 1 -> paper space; 0 -> model space
        temp_model_space = self._layout_spaces[0]
        model_space = self.get_entity_space(model_space_key)
        paper_space = self.get_entity_space(paper_space_key)

        update_entity_tags(temp_model_space)  # just for entities in the temporary model space
        distribute(temp_model_space)  # move entities from temp space into model or paper space

        del self._layout_spaces[0]  # just delete the temporary model space, not the entities itself

    def get_entity_space(self, key):
        """ Get entity space by *key* or create new entity space.
        """
        try:
            entity_space = self._layout_spaces[key]
        except KeyError:  # create new entity space; internal exception
            entity_space = EntitySpace(self._entitydb)
            self.set_entity_space(key, entity_space)
        return entity_space

    def set_entity_space(self, key, entity_space):
        self._layout_spaces[key] = entity_space

    def store_tags(self, tags):
        """ Store *tags* in associated layout entity space.
        """
        # AC1018: if entities have no owner tag (330) (thanks Autodesk for making the owner tag not mandatory), store
        # this entities in a temporary model space with layout_key = 0
        # this will be resolved later in LayoutSpaces.repair_owner_tags()
        entity_space = self.get_entity_space(self._get_key(tags))
        entity_space.store_tags(tags)

    def write(self, tagwriter, keys=None):
        """ Write all entity spaces to *stream*.

        If *keys* is not *None*, write only entity spaces defined in *keys*.
        """
        layout_spaces = self._layout_spaces
        if keys is None:
            keys = set(layout_spaces.keys())

        for key in keys:
            layout_spaces[key].write(tagwriter)

    def delete_entity(self, entity):
        """ Delete *entity* from associated layout entity space.
        Type of *entity* has to be DXFEntity() or inherited.
        """
        key = self._get_key(entity.tags)
        try:
            entity_space = self._layout_spaces[key]
        except KeyError:  # ignore; internal exception
            pass
        else:
            entity_space.delete_entity(entity)

    def delete_entity_space(self, key):
        """ Delete layout entity space *key*.
        """
        entity_space = self._layout_spaces[key]
        entity_space.delete_all_entities()
        del self._layout_spaces[key]

    def delete_all_entities(self):
        """ Delete all entities from all layout entity spaces.
        """
        # Do not delete the entity space objects itself, just remove all entities from all entity spaces.
        for entity_space in self._layout_spaces.values():
            entity_space.delete_all_entities()
