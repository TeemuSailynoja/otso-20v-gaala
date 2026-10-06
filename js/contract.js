// The browser half of the data contract — see site_contract.py for the rules and
// why they are written twice. The grammar:
//
//   "int" "number" "str" "bool" "null"     a scalar, by JSON type
//   {"obj": {field: spec, ...}}            object; every listed field required,
//                                          no unlisted field allowed
//   {"optional": spec}                     field may be absent (obj only)
//   {"map": spec}                          object with any keys, values match
//   {"list": spec}                         array, every item matches
//   {"any": [spec, ...]}                   at least one matches
//
// This file is pure: no fetch, no DOM. tests/test_contract.py runs it under node
// over the built site_data/, so the Python and the JS checker are held to the
// same answer rather than assumed to agree.

export class ContractError extends Error {
    constructor(file, problems) {
        const shown = problems.slice(0, 8);
        super(`${file}: ${problems.length} problem${problems.length === 1 ? '' : 's'} — `
            + shown.join('; ')
            + (problems.length > shown.length ? `; …${problems.length - shown.length} more` : ''));
        this.name = 'ContractError';
        this.file = file;
        this.problems = problems;
    }
}

const isInt = (v) => Number.isInteger(v);
const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

function kindOf(value) {
    // Same vocabulary as _kind() in site_contract.py — a failure has to read the
    // same in the build log and in the browser console.
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'boolean') return 'bool';
    if (typeof value === 'string') return 'str';
    if (typeof value === 'number') return Number.isInteger(value) ? 'int' : 'number';
    return typeof value;
}

function describe(spec) {
    if (typeof spec === 'string') return spec;
    if (spec && typeof spec === 'object') {
        if ('obj' in spec) return 'object';
        if ('map' in spec) return 'object';
        if ('list' in spec) return 'array';
        if ('any' in spec) return spec.any.map(describe).join(' or ');
        if ('optional' in spec) return describe(spec.optional);
    }
    return JSON.stringify(spec);
}

// Returns an array of "path: problem" strings. Empty means the value fits.
export function validate(value, spec, path = '') {
    if (typeof spec === 'string') {
        const ok = {
            int: isInt,
            number: isNumber,
            str: (v) => typeof v === 'string',
            bool: (v) => typeof v === 'boolean',
            null: (v) => v === null,
        }[spec](value);
        return ok ? [] : [`${path || '<root>'}: expected ${spec}, got ${kindOf(value)}`];
    }

    if (!spec || typeof spec !== 'object') return [`${path || '<root>'}: bad spec`];

    if ('any' in spec) {
        for (const alternative of spec.any) {
            if (validate(value, alternative, path).length === 0) return [];
        }
        return [`${path || '<root>'}: expected ${describe(spec)}, got ${kindOf(value)}`];
    }

    if ('obj' in spec) {
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            return [`${path || '<root>'}: expected an object, got ${kindOf(value)}`];
        }
        const fields = spec.obj;
        const problems = [];
        for (const field of Object.keys(fields)) {
            let fieldSpec = fields[field];
            const optional = fieldSpec && typeof fieldSpec === 'object' && 'optional' in fieldSpec;
            if (optional) fieldSpec = fieldSpec.optional;
            if (!(field in value)) {
                if (!optional) problems.push(`${path || '<root>'}.${field}: missing`);
                continue;
            }
            problems.push(...validate(value[field], fieldSpec, `${path || '<root>'}.${field}`));
        }
        for (const field of Object.keys(value)) {
            if (!(field in fields)) problems.push(`${path || '<root>'}.${field}: not in the schema`);
        }
        return problems;
    }

    if ('map' in spec) {
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
            return [`${path || '<root>'}: expected an object, got ${kindOf(value)}`];
        }
        const problems = [];
        for (const key of Object.keys(value)) {
            problems.push(...validate(value[key], spec.map, `${path || '<root>'}.${key}`));
        }
        return problems;
    }

    if ('list' in spec) {
        if (!Array.isArray(value)) {
            return [`${path || '<root>'}: expected an array, got ${kindOf(value)}`];
        }
        const problems = [];
        value.forEach((item, index) => {
            problems.push(...validate(item, spec.list, `${path || '<root>'}[${index}]`));
        });
        return problems;
    }

    return [`${path || '<root>'}: bad spec`];
}
