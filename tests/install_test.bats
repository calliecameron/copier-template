# shellcheck shell=bats

setup() {
    THIS_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")" && pwd)"
    PROJECT_DIR="$(readlink -f "${THIS_DIR}/..")"

    bats_load_library 'bats-support'
    bats_load_library 'bats-assert'
}

run_copier() {
    local REPO="${BATS_TEST_TMPDIR}/foo"
    mkdir "${REPO}"
    # shellcheck disable=SC2164
    cd "${REPO}"
    git init --initial-branch=main .
    git config --local user.name Bar
    git config --local user.email test@example.com
    # shellcheck disable=SC2164
    cd "${PROJECT_DIR}"
    uv run --project "${PROJECT_DIR}" --directory "${REPO}" \
        copier copy --trust --vcs-ref=HEAD \
        "${@}" \
        "${PROJECT_DIR}" "${REPO}"
    # shellcheck disable=SC2164
    cd "${REPO}"
    git add --all
    make
    run git ls-files --others --exclude-standard
    assert_success
    refute_output
    git commit -m 'Foo bar'
}

# bats test_tags=slow
@test "install no options" {
    run_copier \
        --data=project_name=Foo \
        --defaults
}

install_all_options() {
    run_copier \
        --data=project_name=Foo \
        --data=author_name=Bar \
        --data=user_uses_bats=true \
        "--data=max_python_version=${2}" \
        "--data=min_python_version=${1}" \
        --data=user_is_python_package=true \
        --data=user_uses_pytest=true \
        --data=exports_requirements_txt=true \
        --data=user_has_javascript=true \
        --data=user_has_html=true \
        --data=user_has_css=true \
        --data=user_uses_github_actions=true \
        --data=github_repo=foo/bar
}

# bats test_tags=slow
@test "install all options 3.14" {
    install_all_options 3.14 3.14
}

# bats test_tags=slow
@test "install all options 3.13" {
    install_all_options 3.13 3.13
}

# bats test_tags=slow
@test "install all options 3.12" {
    install_all_options 3.12 3.12
}

# bats test_tags=slow
@test "install all options multi" {
    install_all_options 3.12 3.14
}
