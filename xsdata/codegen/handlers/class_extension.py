from typing import Optional

from xsdata.codegen.mixins import RelativeHandlerInterface
from xsdata.codegen.models import Attr
from xsdata.codegen.models import AttrType
from xsdata.codegen.models import Class
from xsdata.codegen.models import Extension
from xsdata.codegen.utils import ClassUtils
from xsdata.exceptions import CodeGenerationError
from xsdata.logger import logger
from xsdata.models.enums import DataType
from xsdata.models.enums import NamespaceType
from xsdata.models.enums import Tag


class ClassExtensionHandler(RelativeHandlerInterface):
    """Reduce class extensions by copying or creating new attributes."""

    __slots__ = ()

    def process(self, target: Class):
        """Iterate and process the target class's extensions in reverser
        order."""
        for extension in list(target.extensions):
            self.process_extension(target, extension)

    def process_extension(self, target: Class, extension: Extension):
        """Slit the process of extension into schema data types and user
        defined types."""
        if extension.type.native:
            self.process_native_extension(target, extension)
        else:
            self.process_dependency_extension(target, extension)

    @classmethod
    def process_native_extension(cls, target: Class, extension: Extension):
        """
        Native type flatten handler.

        In case of enumerations copy the native data type to all enum
        members, otherwise create a default text value with the
        extension attributes.
        """
        if target.is_enumeration:
            cls.replace_attributes_type(target, extension)
        else:
            cls.add_default_attribute(target, extension)

    def process_dependency_extension(self, target: Class, extension: Extension):
        """User defined type flatten handler."""
        source = self.find_dependency(extension.type)
        if not source:
            logger.warning("Missing extension type: %s", extension.type.name)
            target.extensions.remove(extension)
        elif target.is_enumeration:
            self.process_enum_extension(source, target, extension)
        elif not source.is_complex or source.is_enumeration:
            self.process_simple_extension(source, target, extension)
        else:
            self.process_complex_extension(source, target, extension)

    def process_enum_extension(
        self, source: Class, target: Class, ext: Optional[Extension]
    ):
        """
        Process enumeration class extension.

        Extension cases:
            1. Enumeration: copy all attr properties
            2. Simple type: copy value attr properties recursively
            3. Complex type:
                3.1 Target has one enumeration member, convert to complex type
                3.2 Invalid schema.
        """
        if ext:
            target.extensions.remove(ext)

        if source.is_enumeration:
            self.merge_enumerations(source, target)
        elif len(source.attrs) == 1:
            self.merge_enumeration_types(source, target)
        elif len(target.attrs) == 1:
            # We are not an enumeration pal.
            self.convert_to_complex_type(source, target)
        else:
            raise CodeGenerationError("Enumeration class with a complex extension.")

    @classmethod
    def merge_enumerations(cls, source: Class, target: Class):
        source_attrs = {attr.name: attr for attr in source.attrs}
        target.attrs = [
            source_attrs[attr.name].clone() if attr.name in source_attrs else attr
            for attr in target.attrs
        ]

    def merge_enumeration_types(self, source: Class, target: Class):
        source_attr = source.attrs[0]
        for tp in source_attr.types:
            if tp.native:
                for target_attr in target.attrs:
                    target_attr.types.append(tp.clone())
                    target_attr.restrictions.merge(source_attr.restrictions)
            else:
                base = self.find_dependency(tp)
                # It's impossible to have a missing reference now, the
                # source class has passed through AttributeTypeHandler
                # and any missing types have been reset.
                assert base is not None
                self.process_enum_extension(base, target, None)

    @classmethod
    def convert_to_complex_type(cls, source: Class, target: Class):
        default = target.attrs[0].default
        target.attrs = [attr.clone() for attr in source.attrs]
        target.extensions = [ext.clone() for ext in source.extensions]

        for attr in target.attrs:
            if attr.xml_type is None:
                attr.default = default
                attr.fixed = True

    @classmethod
    def process_simple_extension(cls, source: Class, target: Class, ext: Extension):
        """
        Simple flatten extension handler for common classes eg SimpleType,
        Restriction.

        Steps:
            1. If target is source: drop the extension.
            2. If source is enumeration and target isn't create default value attribute.
            3. If both source and target are enumerations copy all attributes.
            4. If both source and target are not enumerations copy all attributes.
            5. If target is enumeration: drop the extension.
        """
        if source is target:
            target.extensions.remove(ext)
        elif source.is_enumeration and not target.is_enumeration:
            cls.add_default_attribute(target, ext)
        elif source.is_enumeration == target.is_enumeration:
            ClassUtils.copy_attributes(source, target, ext)
        else:  # this is an enumeration
            target.extensions.remove(ext)

    @classmethod
    def process_complex_extension(cls, source: Class, target: Class, ext: Extension):
        """
        Complex flatten extension handler for primary classes eg ComplexType,
        Element.

        Compare source and target classes and either remove the
        extension completely, copy all source attributes to the target
        class or leave the extension alone.
        """
        if cls.should_remove_extension(source, target):
            target.extensions.remove(ext)
        elif cls.should_flatten_extension(source, target):
            ClassUtils.copy_attributes(source, target, ext)
        else:
            ext.type.reference = id(source)
            logger.debug("Ignore extension: %s", ext.type.name)

    def find_dependency(self, attr_type: AttrType) -> Optional[Class]:
        """
        Find dependency for the given extension type with priority.

        Search priority: xs:SimpleType >  xs:ComplexType
        """

        conditions = (
            lambda x: x.tag == Tag.SIMPLE_TYPE,
            lambda x: x.tag == Tag.COMPLEX_TYPE,
        )

        for condition in conditions:
            result = self.container.find(attr_type.qname, condition=condition)
            if result:
                return result

        return None

    @classmethod
    def should_remove_extension(cls, source: Class, target: Class) -> bool:
        """
        Return whether the extension should be removed because of some
        violation.

        Violations:
            - Circular Reference
            - Forward Reference
            - MRO Violation A(B), C(B) and extensions includes A, B, C
        """
        # Circular or Forward reference
        if source is target or target in source.inner:
            return True

        # MRO Violation
        collision = {ext.type.qname for ext in target.extensions}
        return any(ext.type.qname in collision for ext in source.extensions)

    @classmethod
    def should_flatten_extension(cls, source: Class, target: Class) -> bool:
        """
        Return whether the extension should be flattened because of rules.

        Rules:
            1. Source doesn't have a parent class
            2. Source class is a simple type
            3. Source class has a suffix attr and target has its own attrs
            4. Target class has a suffix attr
            5. Target restrictions parent attrs in different sequential order
            6. Target restricts parent attr with a not matching type.
        """

        if not source.extensions and (
            source.is_simple_type
            or target.has_suffix_attr
            or (source.has_suffix_attr and target.attrs)
            or not cls.validate_type_overrides(source, target)
            or not cls.validate_sequential_order(source, target)
        ):
            return True

        return False

    @classmethod
    def validate_type_overrides(cls, source: Class, target: Class) -> bool:
        """Validate every override is using a subset of the parent attr
        types."""
        for attr in target.attrs:
            src_attr = ClassUtils.find_attr(source, attr.name)
            if src_attr and any(tp not in src_attr.types for tp in attr.types):
                return False

        return True

    @classmethod
    def validate_sequential_order(cls, source: Class, target: Class) -> bool:
        """
        Validate sequential attributes are in the same order in the parent
        class.

        Dataclasses fields ordering follows the python mro pattern, the
        parent fields are always first and they are updated if the
        subclass is overriding any of them but the overall ordering
        doesn't change!
        """
        sequence = [attr.name for attr in target.attrs if attr.restrictions.sequential]
        if len(sequence) > 1:
            compare = [attr.name for attr in source.attrs if attr.name in sequence]
            if compare and compare != sequence:
                return False

        return True

    @classmethod
    def replace_attributes_type(cls, target: Class, extension: Extension):
        """Replace all target attributes types with the extension's type and
        remove it from the target class extensions."""

        for attr in target.attrs:
            attr.types.clear()
            attr.types.append(extension.type.clone())
        target.extensions.remove(extension)

    @classmethod
    def add_default_attribute(cls, target: Class, extension: Extension):
        """Add a default value field to the given class based on the extension
        type."""
        if extension.type.datatype != DataType.ANY_TYPE:
            tag = Tag.EXTENSION
            name = "@value"
            namespace = None
        else:
            tag = Tag.ANY
            name = "@any_element"
            namespace = NamespaceType.ANY_NS

        attr = cls.get_or_create_attribute(target, name, tag)
        attr.types.append(extension.type.clone())
        attr.restrictions.merge(extension.restrictions)
        attr.namespace = namespace
        target.extensions.remove(extension)

    @classmethod
    def get_or_create_attribute(cls, target: Class, name: str, tag: str) -> Attr:
        """Find or create for the given parameters an attribute in the target
        class."""

        attr = ClassUtils.find_attr(target, name)
        if attr is None:
            attr = Attr(name=name, tag=tag)
            attr.restrictions.min_occurs = 1
            attr.restrictions.max_occurs = 1
            target.attrs.insert(0, attr)

        return attr
